"""Lưu bền miễn phí trên Hugging Face: đồng bộ SQLite với một Dataset repo riêng tư.

Ổ đĩa của Space bị xoá mỗi lần khởi động lại ⇒ khi khởi động tải bản mới nhất về, rồi đẩy bản sao
lên mỗi HF_SYNC_MINUTES phút (chỉ khi dữ liệu đã đổi) và một lần cuối khi Space tắt.

Biến môi trường: HF_TOKEN (Secret, quyền ghi Dataset), HF_BACKUP_REPO (vd "user/match-performance-data"),
HF_SYNC_MINUTES (mặc định 10).
"""
from __future__ import annotations

import gzip
import hashlib
import logging
import os
import shutil
import sqlite3
import tempfile
import threading
from pathlib import Path

from . import config

log = logging.getLogger("cloud.hfsync")
REMOTE_NAME = "app.db.gz"


def enabled() -> bool:
    return bool(os.environ.get("HF_TOKEN") and os.environ.get("HF_BACKUP_REPO"))


def _api():
    from huggingface_hub import HfApi
    return HfApi(token=os.environ["HF_TOKEN"])


def _repo() -> str:
    return os.environ["HF_BACKUP_REPO"]


def ensure_repo() -> None:
    """Tạo Dataset nếu chưa có và LUÔN ép về riêng tư (chứa email + mật khẩu đã băm).
    huggingface_hub 2.x: dùng `visibility` — tham số `private` cũ bị bỏ qua (đã gặp: Dataset bị tạo public)."""
    api = _api()
    api.create_repo(_repo(), repo_type="dataset", visibility="private", exist_ok=True)
    if not api.repo_info(_repo(), repo_type="dataset").private:
        api.update_repo_settings(_repo(), repo_type="dataset", visibility="private")
        log.warning("Dataset sao lưu đang public — đã chuyển về private")


def _snapshot(db_path: Path, target: Path) -> str:
    """Sao chép nhất quán (API backup của SQLite) rồi nén. → SHA-256 của bản sao chưa nén."""
    raw = target.with_suffix(".raw")
    src, dst = sqlite3.connect(str(db_path)), sqlite3.connect(str(raw))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    with raw.open("rb") as fin, gzip.open(target, "wb", compresslevel=6) as fout:
        shutil.copyfileobj(fin, fout)
    raw.unlink()
    return digest


def restore(settings: config.Settings) -> bool:
    """Tải bản sao mới nhất từ Dataset nếu DB cục bộ chưa có. → True nếu đã khôi phục."""
    if settings.db_path.exists() and settings.db_path.stat().st_size > 0:
        return False
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import EntryNotFoundError, RepositoryNotFoundError
    try:
        path = hf_hub_download(_repo(), REMOTE_NAME, repo_type="dataset", token=os.environ["HF_TOKEN"])
    except (EntryNotFoundError, RepositoryNotFoundError):
        log.info("Dataset chưa có bản sao lưu — bắt đầu với DB rỗng")
        return False
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = settings.db_path.with_suffix(".restoring")
    with gzip.open(path, "rb") as fin, tmp.open("wb") as fout:
        shutil.copyfileobj(fin, fout)
    check = sqlite3.connect(str(tmp))
    try:
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("bản sao lưu trên Dataset bị hỏng")
    finally:
        check.close()
    tmp.replace(settings.db_path)
    log.info("Đã khôi phục DB từ dataset %s", _repo())
    return True


class Syncer:
    def __init__(self, settings: config.Settings, minutes: int | None = None):
        self.settings = settings
        self.minutes = minutes or max(1, int(os.environ.get("HF_SYNC_MINUTES", "10") or 10))
        self.stop = threading.Event()
        self.last_digest: str | None = None
        self.lock = threading.Lock()

    def push(self, reason: str = "periodic") -> bool:
        """Đẩy bản sao lên Dataset nếu dữ liệu đổi so với lần trước. → True nếu đã đẩy."""
        if not self.settings.db_path.exists():
            return False
        with self.lock, tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / REMOTE_NAME
            digest = _snapshot(self.settings.db_path, target)
            if digest == self.last_digest:
                return False
            _api().upload_file(path_or_fileobj=str(target), path_in_repo=REMOTE_NAME, repo_id=_repo(),
                               repo_type="dataset", commit_message=f"backup ({reason})")
            self.last_digest = digest
            log.info("Đã đẩy bản sao DB lên dataset (%s)", reason)
            return True

    def loop(self) -> None:
        while not self.stop.wait(self.minutes * 60):
            try:
                self.push()
            except Exception as exc:                 # lỗi mạng tạm thời: thử lại ở lần sau
                log.error("Đẩy bản sao lên dataset thất bại: %s", exc)
