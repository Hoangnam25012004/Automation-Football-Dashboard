"""Điểm khởi chạy trên Hugging Face Spaces (Docker Space, một container).

  python -m cloud.hf_main

1. APP_BASE_URL lấy từ SPACE_HOST (Hugging Face tự đặt) nếu chưa có.
2. Khôi phục DB từ Dataset riêng tư (cloud.hfsync) — ổ đĩa Space không bền.
3. Tạo admin đầu tiên từ Secret BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD nếu DB chưa có admin
   (Space không có shell để chạy `python -m cloud.admin`).
4. Chạy worker + vòng đồng bộ (thread) và web (Uvicorn, cổng 7860); khi tắt: đẩy bản sao lần cuối.
"""
from __future__ import annotations

import logging
import os
import threading

log = logging.getLogger("cloud.hf")


def bootstrap_admin(settings) -> None:
    email, password = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", ""), os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not email or not password:
        return
    from . import auth
    from .db import connect, migrate
    from .errors import ApiError
    conn = connect(settings.db_path)
    try:
        migrate(conn)
        if conn.execute("SELECT 1 FROM users WHERE role = 'admin' AND status = 'active'").fetchone():
            return                                            # đã có admin: không đụng tới (không ghi đè mật khẩu)
        auth.create_admin(conn, email, password)
        log.info("Đã tạo admin đầu tiên từ Secret BOOTSTRAP_ADMIN_EMAIL")
    except ApiError as exc:
        log.error("Không tạo được admin đầu tiên: %s %s", exc.message, exc.hint)
    finally:
        conn.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    host = os.environ.get("SPACE_HOST", "")
    if host and not os.environ.get("APP_BASE_URL"):
        os.environ["APP_BASE_URL"] = "https://" + host.split(",")[0].strip()
    os.environ.setdefault("TRUST_PROXY", "1")

    import uvicorn

    from . import config, hfsync
    from .app import create_app
    from .worker import Worker

    settings = config.load()
    syncer = None
    if hfsync.enabled():
        hfsync.ensure_repo()
        hfsync.restore(settings)
        syncer = hfsync.Syncer(settings)
    else:
        log.warning("HF_TOKEN / HF_BACKUP_REPO chưa đặt ⇒ dữ liệu MẤT khi Space khởi động lại")
    bootstrap_admin(settings)

    app = create_app(settings)
    worker = Worker(settings)
    threading.Thread(target=worker.loop, name="cloud-worker", daemon=True).start()
    if syncer:
        threading.Thread(target=syncer.loop, name="hf-sync", daemon=True).start()
    from . import diag
    diag.run_in_background()                                  # chỉ chạy khi có biến FS_DIAG_URL
    port = int(os.environ.get("PORT", "7860"))
    log.info("Match Performance (Hugging Face) → %s", settings.base_url)
    try:
        uvicorn.run(app, host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*",
                    access_log=False, log_level="info")
    finally:
        worker.stop.set()
        if syncer:
            syncer.stop.set()
            try:
                syncer.push("shutdown")
            except Exception as exc:
                log.error("Đẩy bản sao cuối cùng thất bại: %s", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
