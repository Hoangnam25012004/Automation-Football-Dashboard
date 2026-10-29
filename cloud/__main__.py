"""Chạy thử bản cloud trên máy dev: web + worker trong cùng một tiến trình.

  python -m cloud [--port 8000] [--no-worker]

Triển khai thật dùng 2 container riêng (deploy/docker-compose.yml).
"""
from __future__ import annotations

import argparse
import logging
import os
import threading


def main() -> int:
    ap = argparse.ArgumentParser(description="Match Performance — bản cloud (dev)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--no-worker", action="store_true", help="không chạy worker trong tiến trình này")
    args = ap.parse_args()
    os.environ.setdefault("APP_BASE_URL", f"http://{args.host}:{args.port}")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    import uvicorn

    from .app import create_app
    from .worker import Worker

    app = create_app()
    if not args.no_worker:
        worker = Worker()
        threading.Thread(target=worker.loop, name="cloud-worker", daemon=True).start()
    print(f"Match Performance (cloud, dev) → {os.environ['APP_BASE_URL']}")
    uvicorn.run(app, host=args.host, port=args.port, access_log=False, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
