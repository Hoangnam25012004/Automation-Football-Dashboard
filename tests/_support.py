"""Tiện ích dùng chung cho test: đường dẫn, Playwright, ghi nhận lỗi console."""
from __future__ import annotations

import contextlib
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "match_report.html"
OUTPUT = ROOT / "tests" / "output"          # gitignored: file tạm, ảnh, PDF tải về
FIXTURES = ROOT / "tests" / "fixtures"
GOLDEN = ROOT / "tests" / "golden"

LIVE = os.environ.get("FS_LIVE") == "1"      # test chạm tới flashscore.com thật
SKIP_PDF = os.environ.get("FS_SKIP_PDF") == "1"

# Chặn khi test UI: Tesseract (OCR của demo — nặng, không ảnh hưởng DOM được so) và web font.
_BLOCK = ("tesseract", "fonts.googleapis.com", "fonts.gstatic.com")


def block_noise(page) -> None:
    def handler(route):
        url = route.request.url
        if any(p in url for p in _BLOCK):
            return route.abort()
        return route.continue_()
    page.route("**/*", handler)


class ConsoleLog:
    """Thu lỗi JS (pageerror) và console.error của trang; bỏ qua lỗi tải tài nguyên bị chặn."""

    def __init__(self, page):
        self.errors: list[str] = []
        page.on("pageerror", lambda exc: self.errors.append(f"pageerror: {exc}"))
        page.on("console", self._on_console)

    def _on_console(self, msg) -> None:
        if msg.type == "error" and not msg.text.startswith("Failed to load resource"):
            self.errors.append(f"console.error: {msg.text}")


def output_dir() -> Path:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    return OUTPUT


@contextlib.contextmanager
def running_server(runner=None):
    """Chạy server.py trên cổng ngẫu nhiên trong thread nền. runner=None ⇒ crawler thật."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import server as server_module
    httpd = server_module.make_server(0, runner)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def http(method: str, url: str, body: bytes | None = None, headers: dict | None = None):
    """→ (status, headers, body bytes) — không ném lỗi với mã 4xx/5xx."""
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        with exc:
            return exc.code, dict(exc.headers), exc.read()


def post_json(base: str, payload, headers: dict | None = None):
    status, hdrs, body = http("POST", base + "/api/matches", json.dumps(payload).encode("utf-8"),
                              {"Content-Type": "application/json", **(headers or {})})
    return status, json.loads(body.decode("utf-8"))
