"""Tiến trình worker: lấy job từ SQLite → DataSource.fetch (crawler, Playwright sync) → lưu thư viện.

Chạy:  python -m cloud.worker
Một job mỗi lần (Flashscore là nút thắt). Tiến trình riêng ⇒ Chromium lỗi/chiếm RAM không kéo sập web.
"""
from __future__ import annotations

import logging
import signal
import threading
import time
import traceback

from crawler.errors import CrawlError

from . import config, datasource, jobs
from .db import connect, migrate, now_ts, set_setting, tx
from .errors import ApiError

log = logging.getLogger("cloud.worker")
POLL_S = 1.0
HEARTBEAT_S = 10.0
PROGRESS_MIN_INTERVAL_S = 0.5


class Worker:
    def __init__(self, settings: config.Settings | None = None):
        self.settings = settings or config.load()
        self.conn = connect(self.settings.db_path)
        migrate(self.conn)
        self.stop = threading.Event()
        self._last_beat = 0.0

    def beat(self, force: bool = False) -> None:
        if force or now_ts() - self._last_beat >= HEARTBEAT_S:
            set_setting(self.conn, "worker_heartbeat", now_ts())
            self._last_beat = now_ts()

    def run_one(self) -> bool:
        """Xử lý 1 job nếu có. → True nếu đã xử lý một job."""
        job = jobs.claim(self.conn)
        if job is None:
            return False
        source = datasource.get()
        ref = datasource.SourceRef(job["source"], job["match_key"], job["url"])
        started = time.monotonic()
        last = [0.0]
        log.info("job %s ▶ %s:%s", job["id"], job["source"], job["match_key"])

        def progress(p: dict) -> None:
            now = time.monotonic()
            if now - last[0] >= PROGRESS_MIN_INTERVAL_S or p.get("phase") == "done":
                last[0] = now
                jobs.set_progress(self.conn, job["id"], p)
            self.beat()

        try:
            result = source.fetch(ref, progress)
            jobs.finish_ok(self.conn, job, result)
            with tx(self.conn):
                jobs.record_source_result(self.conn, self.settings, blocked=False)
            codes = ", ".join(w["code"] for w in result.get("warnings", [])) or "không có"
            log.info("job %s ✓ %.1f s · cảnh báo: %s", job["id"], time.monotonic() - started, codes)
        except (CrawlError, ApiError) as exc:
            jobs.finish_error(self.conn, job, exc.to_dict())
            with tx(self.conn):
                jobs.record_source_result(self.conn, self.settings, blocked=getattr(exc, "code", "") == "E_BLOCKED")
            log.warning("job %s ✗ %s: %s", job["id"], exc.code, exc.message)
        except Exception:                                # lỗi không lường trước: không được làm chết worker
            log.error("job %s ✗ E_INTERNAL\n%s", job["id"], traceback.format_exc())
            jobs.finish_error(self.conn, job, CrawlError("E_INTERNAL").to_dict())
        return True

    def loop(self) -> None:
        log.info("worker sẵn sàng (DB %s)", self.settings.db_path)
        while not self.stop.is_set():
            self.beat()
            try:
                worked = self.run_one()
            except Exception:
                log.error("vòng lặp worker lỗi\n%s", traceback.format_exc())
                worked = False
            if not worked:
                self.stop.wait(POLL_S)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    worker = Worker()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: worker.stop.set())
        except (ValueError, OSError):
            pass
    worker.loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
