"""Sao lưu SQLite (API backup — an toàn khi đang chạy), nén gzip, giữ N bản, tuỳ chọn tải lên Object Storage.

  python -m cloud.backup            → /data/backups/app-YYYYmmdd-HHMMSS.db.gz (+ PUT lên BACKUP_PAR_URL nếu có)
  python -m cloud.backup --restore FILE.db.gz   (chỉ khi web + worker đã dừng)

BACKUP_PAR_URL: "Pre-Authenticated Request" (ghi) của bucket Oracle Object Storage, dạng
https://objectstorage.<region>.oraclecloud.com/p/<token>/n/<namespace>/b/<bucket>/o/  — tên file được nối vào cuối.
"""
from __future__ import annotations

import argparse
import gzip
import shutil
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import config


def make_backup(settings: config.Settings) -> Path:
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    raw = settings.backup_dir / f"app-{stamp}.db"
    src = sqlite3.connect(str(settings.db_path))
    dst = sqlite3.connect(str(raw))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    target = raw.with_suffix(".db.gz")
    with raw.open("rb") as fin, gzip.open(target, "wb", compresslevel=6) as fout:
        shutil.copyfileobj(fin, fout)
    raw.unlink()
    backups = sorted(settings.backup_dir.glob("app-*.db.gz"))
    for old in backups[:-settings.backup_keep]:
        old.unlink()
    return target


def upload(settings: config.Settings, path: Path) -> None:
    if not settings.backup_par_url:
        return
    url = settings.backup_par_url.rstrip("/") + "/" + path.name
    request = urllib.request.Request(url, data=path.read_bytes(), method="PUT",
                                     headers={"Content-Type": "application/gzip"})
    with urllib.request.urlopen(request, timeout=120) as response:
        if response.status >= 300:
            raise OSError(f"upload failed: HTTP {response.status}")


def restore(settings: config.Settings, archive: Path) -> None:
    tmp = settings.db_path.with_suffix(".restoring")
    with gzip.open(archive, "rb") as fin, tmp.open("wb") as fout:
        shutil.copyfileobj(fin, fout)
    check = sqlite3.connect(str(tmp))
    try:
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SystemExit("✗ Bản sao lưu bị hỏng (integrity_check).")
    finally:
        check.close()
    for suffix in ("-wal", "-shm"):
        Path(str(settings.db_path) + suffix).unlink(missing_ok=True)
    tmp.replace(settings.db_path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--restore", type=Path, help="khôi phục từ file .db.gz (dừng web + worker trước)")
    args = ap.parse_args()
    settings = config.load()
    if args.restore:
        restore(settings, args.restore)
        print(f"✓ Đã khôi phục {settings.db_path} từ {args.restore}")
        return 0
    path = make_backup(settings)
    try:
        upload(settings, path)
    except OSError as exc:
        from . import mail
        mail.alert_admin(settings, "Backup upload failed", str(exc))
        print(f"✗ Không tải được bản sao lưu lên Object Storage: {exc}", file=sys.stderr)
        return 1
    print(f"✓ {path} ({path.stat().st_size:,} byte){' → Object Storage' if settings.backup_par_url else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
