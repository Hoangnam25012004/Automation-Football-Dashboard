"""Server local: phục vụ match_report.html + API crawl 1 link Flashscore (design doc §3, §4).

Chạy:   python server.py        → mở http://127.0.0.1:8778
Biến môi trường: FS_PORT (mặc định 8778) · FS_HEADLESS=0 (hiện trình duyệt khi crawl) ·
                 FS_DEBUG=1 (lưu HTML của bước lỗi vào debug/)

Chỉ bind 127.0.0.1, không bật CORS. Mọi việc với trình duyệt chạy trong MỘT worker thread
(Playwright sync không an toàn đa luồng); luồng HTTP chỉ đọc/ghi JobStore.
"""
from __future__ import annotations

import json
import os
import queue
import re
import secrets
import sys
import threading
import time
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit

from crawler import CrawlError, crawl
from crawler.urls import parse_match_url

ROOT = Path(__file__).resolve().parent
HTML_FILE = ROOT / "match_report.html"
STATIC_ROUTES = {"/": HTML_FILE, "/match_report.html": HTML_FILE}
DEFAULT_PORT = 8778
MAX_BODY = 2048
MAX_ACTIVE_JOBS = 2               # 1 đang chạy + 1 chờ (design doc §3.5)
JOB_TTL_S = 30 * 60
MAX_FINISHED_KEPT = 20
_JOB_PATH = re.compile(r"^/api/matches/([A-Za-z0-9_-]{6,32})$")


def log(message: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


class Job:
    def __init__(self, url: str):
        self.id = secrets.token_hex(4)
        self.url = url
        self.status = "queued"
        self.progress = {"phase": "queued", "done": 0, "total": 10, "message": "Waiting for the previous match…"}
        self.result = None
        self.error = None
        self.created = time.time()
        self.finished = None

    def to_dict(self) -> dict:
        data = {"jobId": self.id, "status": self.status, "progress": self.progress}
        if self.status == "done":
            data["warnings"] = self.result.get("warnings", [])
            data["result"] = self.result
        if self.status == "error":
            data["error"] = self.error
        return data


class JobStore:
    def __init__(self, runner):
        self._runner = runner
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._pending: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._worker, name="crawl-worker", daemon=True).start()

    def submit(self, url: str) -> Job:
        with self._lock:
            self._collect_garbage()
            active = sum(1 for j in self._jobs.values() if j.status in ("queued", "running"))
            if active >= MAX_ACTIVE_JOBS:
                raise CrawlError("E_BUSY")
            job = Job(url)
            self._jobs[job.id] = job
        self._pending.put(job.id)
        return job

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return json.loads(json.dumps(job.to_dict())) if job else None

    def _collect_garbage(self) -> None:
        """Bỏ job đã xong quá JOB_TTL_S, và giữ tối đa MAX_FINISHED_KEPT job đã xong mới nhất."""
        now = time.time()
        finished = sorted((j for j in self._jobs.values() if j.finished), key=lambda j: j.finished)
        excess = max(0, len(finished) - MAX_FINISHED_KEPT)
        for index, job in enumerate(finished):
            if index < excess or now - job.finished > JOB_TTL_S:
                del self._jobs[job.id]

    def _worker(self) -> None:
        while True:
            job_id = self._pending.get()
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    continue
                job.status = "running"
            started = time.monotonic()
            log(f"job {job.id} ▶ {job.url}")

            def on_progress(p: dict, job: Job = job) -> None:
                with self._lock:
                    job.progress = p
                log(f"job {job.id}   [{p['done']}/{p['total']}] {p['message']}")

            try:
                result = self._runner(job.url, on_progress)
                with self._lock:
                    job.result, job.status = result, "done"
                codes = ", ".join(w["code"] for w in result.get("warnings", [])) or "không có"
                log(f"job {job.id} ✓ xong sau {time.monotonic() - started:.1f} s · cảnh báo: {codes}")
            except CrawlError as exc:
                with self._lock:
                    job.error, job.status = exc.to_dict(), "error"
                log(f"job {job.id} ✗ {exc.code}: {exc.message} ({exc.hint})")
            except Exception:                       # lỗi không lường trước: không được làm chết worker
                traceback.print_exc()
                with self._lock:
                    job.error, job.status = CrawlError("E_INTERNAL").to_dict(), "error"
                log(f"job {job.id} ✗ E_INTERNAL (xem traceback ở trên)")
            finally:
                with self._lock:
                    job.finished = time.time()


class Handler(BaseHTTPRequestHandler):
    server_version = "FootballDashboard/1.0"

    # ---- helpers ----
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, status: int, code: str, message: str, hint: str = "") -> None:
        self._json(status, {"error": {"code": code, "message": message, "hint": hint}})

    def _allowed_hosts(self) -> set[str]:
        port = self.server.server_address[1]
        return {f"127.0.0.1:{port}", f"localhost:{port}"}

    def _host_ok(self) -> bool:
        if self.headers.get("Host", "") in self._allowed_hosts():
            return True
        self._error(403, "E_FORBIDDEN", "Open the dashboard from http://127.0.0.1 only.")
        return False

    # ---- routes ----
    def do_GET(self) -> None:
        if not self._host_ok():
            return
        path = urlsplit(self.path).path
        if path in STATIC_ROUTES:
            return self._send(200, STATIC_ROUTES[path].read_bytes(), "text/html; charset=utf-8")
        if path == "/api/health":
            return self._json(200, {"ok": True, "playwright": version("playwright")})
        match = _JOB_PATH.match(path)
        if match:
            job = self.server.store.get(match.group(1))
            if job is None:
                return self._error(404, "E_JOB_NOT_FOUND", "That request is no longer known to the server.",
                                   "Start again with Generate report.")
            return self._json(200, job)
        if path.startswith("/api/"):
            return self._error(404, "E_NOT_FOUND", "Unknown API endpoint.")
        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        if not self._host_ok():
            return
        if urlsplit(self.path).path != "/api/matches":
            return self._error(404, "E_NOT_FOUND", "Unknown API endpoint.")
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{h}" for h in self._allowed_hosts()}:
            return self._error(403, "E_FORBIDDEN", "Requests from other websites are not allowed.")
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type != "application/json":
            return self._error(415, "E_UNSUPPORTED_MEDIA_TYPE", "Send the link as JSON.")
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = -1
        if length <= 0 or length > MAX_BODY:
            return self._error(413 if length > MAX_BODY else 400, "E_BAD_REQUEST", "Request body is missing or too large.")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            url = payload["url"]
            if not isinstance(url, str):
                raise TypeError("url must be a string")
        except (ValueError, KeyError, TypeError, UnicodeDecodeError):
            exc = CrawlError("E_URL_INVALID")
            return self._json(exc.status, {"error": exc.to_dict()})
        try:
            parse_match_url(url)                    # từ chối ngay, không xếp hàng link sai
            job = self.server.store.submit(url.strip())
        except CrawlError as exc:
            return self._json(exc.status, {"error": exc.to_dict()})
        self._json(202, {"jobId": job.id, "status": job.status})

    def log_message(self, fmt: str, *args) -> None:
        pass                                        # log theo job ở JobStore, không log từng lần poll


def make_server(port: int = DEFAULT_PORT, runner=None) -> ThreadingHTTPServer:
    """Tạo server (port=0 ⇒ cổng ngẫu nhiên, dùng cho test). runner(url, progress) mặc định là crawl."""
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.store = JobStore(runner or (lambda url, progress: crawl(url, progress=progress)))
    return server


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    port = int(os.environ.get("FS_PORT", DEFAULT_PORT))
    try:
        server = make_server(port)
    except OSError as exc:
        print(f"✗ Không mở được cổng {port}: {exc}. Đặt FS_PORT để dùng cổng khác.")
        return 1
    log(f"Football Dashboard đang chạy: http://127.0.0.1:{port}  (Ctrl+C để dừng)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Đang dừng…")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
