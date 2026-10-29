"""Harness cho test bản cloud: server Uvicorn thật (cổng ngẫu nhiên, DB tạm) + nguồn dữ liệu giả từ fixture.

Không chạm flashscore.com. Cần `pip install -r requirements-cloud.txt`; thiếu ⇒ các test cloud tự bỏ qua.
"""
from __future__ import annotations

import contextlib
import copy
import http.cookiejar
import importlib.util
import json
import re
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from tests import _support

CLOUD_DEPS = all(importlib.util.find_spec(m) for m in ("fastapi", "uvicorn"))
FIXTURE_MIDS = ("vLuGlk0n", "GGiPsLP1", "d8pxv90m", "tW4rOkzg")
LINKS = {
    "vLuGlk0n": "https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/?mid=vLuGlk0n",
    "GGiPsLP1": "https://www.flashscore.com/match/football/malaga-25tIqYiJ/villarreal-lUatW5jE/?mid=GGiPsLP1",
    "d8pxv90m": "https://www.flashscore.com/match/football/altglienicke-EP8ggpyE/wolfsburg-nwkTahLL/?mid=d8pxv90m",
    "tW4rOkzg": "https://www.flashscore.com/match/football/coventry-GOvB22xg/newcastle-utd-p6ahwuwJ/?mid=tW4rOkzg",
}
PASSWORD = "correct-horse-battery"


def fixture_result(mid: str) -> dict:
    return json.loads((_support.FIXTURES / mid / "result.json").read_text(encoding="utf-8"))


class FakeSource:
    """Như FlashscoreSource nhưng fetch trả fixture; `fail` = danh sách mã lỗi lần lượt ném ra."""

    name = "flashscore"

    def __init__(self):
        from cloud.datasource import FlashscoreSource
        self._real = FlashscoreSource()
        self.fail: list[str] = []
        self.calls: list[str] = []
        self.delay = 0.0

    def parse_ref(self, url):
        return self._real.parse_ref(url)

    def fetch(self, ref, progress):
        from crawler.errors import CrawlError
        self.calls.append(ref.key)
        progress({"phase": "player_stats", "done": 3, "total": 11, "message": "Reading player stats · Attack (3/7)…"})
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise CrawlError(self.fail.pop(0))
        return copy.deepcopy(fixture_result(ref.key if ref.key in FIXTURE_MIDS else "vLuGlk0n"))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Client:
    """HTTP client có cookie jar; tự gửi X-CSRF-Token (từ cookie fs_csrf) và Origin cho lệnh ghi."""

    def __init__(self, base: str, origin: str | None = None):
        self.base = base
        self.origin = origin if origin is not None else base
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf_override: str | None = None

    def cookie(self, name: str) -> str | None:
        return next((c.value for c in self.jar if c.name == name), None)

    def request(self, method: str, path: str, body=None, headers: dict | None = None, csrf: bool = True):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        hdrs = {"Accept": "application/json"}
        if data is not None:
            hdrs["Content-Type"] = "application/json"
        if method != "GET":
            if self.origin:
                hdrs["Origin"] = self.origin
            if csrf:
                hdrs["X-CSRF-Token"] = self.csrf_override if self.csrf_override is not None else (self.cookie("fs_csrf") or "")
        hdrs.update(headers or {})
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=hdrs)
        try:
            with self.opener.open(req, timeout=30) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw and r.headers.get_content_type() == "application/json" else raw), dict(r.headers)
        except urllib.error.HTTPError as e:
            with e:
                raw = e.read()
                try:
                    payload = json.loads(raw)
                except ValueError:
                    payload = raw
                return e.code, payload, dict(e.headers)

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body if body is not None else {}, **kw)

    def delete(self, path, body=None, **kw):
        return self.request("DELETE", path, body if body is not None else {}, **kw)

    def login(self, email: str, password: str = PASSWORD):
        return self.post("/api/auth/login", {"email": email, "password": password})


class CloudServer:
    """with CloudServer(background_worker=False) as srv: srv.base, srv.settings, srv.source, srv.run_jobs()"""

    def __init__(self, background_worker: bool = False, **overrides):
        self.background_worker = background_worker
        self.overrides = overrides

    def __enter__(self):
        import uvicorn

        from cloud import config, datasource
        from cloud.app import create_app
        from cloud.worker import Worker

        self.tmp = tempfile.TemporaryDirectory(prefix="cloud-test-")
        port = free_port()
        self.base = f"http://127.0.0.1:{port}"
        s = config.Settings()
        s.base_url = self.base
        s.db_path = Path(self.tmp.name) / "app.db"
        s.backup_dir = Path(self.tmp.name) / "backups"
        s.smtp_host = ""
        s.admin_email = ""
        s.registration = "approval"
        s.backup_par_url = ""
        for key, value in self.overrides.items():
            setattr(s, key, value)
        self.settings = s
        self.source = FakeSource()
        self._previous_source = datasource.get()
        datasource.set_source(self.source)
        self.app = create_app(s)
        self.server = uvicorn.Server(uvicorn.Config(self.app, host="127.0.0.1", port=port, log_level="warning",
                                                    access_log=False, lifespan="off"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        self.worker = Worker(s)
        if self.background_worker:
            self.worker_thread = threading.Thread(target=self.worker.loop, daemon=True)
            self.worker_thread.start()
        return self

    def __exit__(self, *exc):
        from cloud import datasource
        self.worker.stop.set()
        if self.background_worker:
            self.worker_thread.join(timeout=10)
        self.server.should_exit = True
        self.thread.join(timeout=10)
        self.worker.conn.close()
        datasource.set_source(self._previous_source)
        with contextlib.suppress(OSError):
            self.tmp.cleanup()

    # ---- tiện ích ----
    def conn(self):
        from cloud.db import connect
        return connect(self.settings.db_path)

    def run_jobs(self, limit: int = 10) -> int:
        n = 0
        while n < limit and self.worker.run_one():
            n += 1
        return n

    def beat(self):
        self.worker.beat(force=True)

    def admin(self, email: str = "admin@example.com") -> Client:
        from cloud import auth
        conn = self.conn()
        try:
            auth.create_admin(conn, email, PASSWORD)
        finally:
            conn.close()
        c = Client(self.base)
        status, body, _ = c.login(email)
        assert status == 200, body
        return c

    def member(self, email: str, quota: int | None = None) -> Client:
        """Đăng ký → xác minh (link trong mail.OUTBOX) → duyệt trực tiếp trong DB → đăng nhập."""
        from cloud import mail
        c = Client(self.base)
        status, body, _ = c.post("/api/auth/register", {"email": email, "password": PASSWORD})
        assert status == 200, body
        token = last_link_token(email, "verify")
        status, body, _ = c.post("/api/auth/verify", {"token": token})
        assert status == 200, body
        conn = self.conn()
        try:
            conn.execute("UPDATE users SET status = 'active', daily_crawl_quota = ? WHERE email = ?", (quota, email))
        finally:
            conn.close()
        status, body, _ = c.login(email)
        assert status == 200, body
        return c


def last_link_token(email: str, kind: str) -> str:
    from cloud import mail
    for msg in reversed(mail.OUTBOX):
        if msg["to"].lower() == email.lower():
            m = re.search(rf"/#/{kind}/([\w-]+)", msg["body"])
            if m:
                return m.group(1)
    raise AssertionError(f"không thấy link {kind} gửi tới {email}")
