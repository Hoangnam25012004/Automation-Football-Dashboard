"""Cấu hình đọc từ biến môi trường (deploy/.env). Giá trị mặc định = chạy thử trên máy dev."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent


def _int(name: str, default: int, low: int = 0, high: int = 10**9) -> int:
    try:
        return max(low, min(high, int(os.environ.get(name, default))))
    except ValueError:
        return default


@dataclass
class Settings:
    base_url: str = field(default_factory=lambda: os.environ.get("APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/"))
    db_path: Path = field(default_factory=lambda: Path(os.environ.get("DB_PATH", str(ROOT / "data" / "app.db"))))
    session_days: int = field(default_factory=lambda: _int("SESSION_DAYS", 14, 1, 90))
    # approval = tự đăng ký + xác minh email + admin duyệt (Q-B ★) · open = không cần duyệt · invite = chỉ admin tạo
    registration: str = field(default_factory=lambda: os.environ.get("REGISTRATION", "approval"))
    quota_user_daily: int = field(default_factory=lambda: _int("QUOTA_USER_DAILY", 10, 0))      # Q-C ★
    quota_global_hourly: int = field(default_factory=lambda: _int("QUOTA_GLOBAL_HOURLY", 30, 0))
    queue_max: int = field(default_factory=lambda: _int("QUEUE_MAX", 20, 1))
    refresh_cooldown_h: int = field(default_factory=lambda: _int("REFRESH_COOLDOWN_H", 6, 0))
    smtp_host: str = field(default_factory=lambda: os.environ.get("SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: _int("SMTP_PORT", 587, 1, 65535))
    smtp_user: str = field(default_factory=lambda: os.environ.get("SMTP_USER", ""))
    smtp_pass: str = field(default_factory=lambda: os.environ.get("SMTP_PASS", ""))
    mail_from: str = field(default_factory=lambda: os.environ.get("MAIL_FROM", "Match Performance <no-reply@localhost>"))
    admin_email: str = field(default_factory=lambda: os.environ.get("ADMIN_EMAIL", ""))   # nhận cảnh báo
    trust_proxy: bool = field(default_factory=lambda: os.environ.get("TRUST_PROXY", "0") == "1")
    backup_dir: Path = field(default_factory=lambda: Path(os.environ.get("BACKUP_DIR", str(ROOT / "data" / "backups"))))
    backup_keep: int = field(default_factory=lambda: _int("BACKUP_KEEP", 14, 1, 365))
    backup_par_url: str = field(default_factory=lambda: os.environ.get("BACKUP_PAR_URL", ""))

    @property
    def origin(self) -> str:
        parts = urlsplit(self.base_url)
        return f"{parts.scheme}://{parts.netloc}"

    @property
    def secure_cookies(self) -> bool:
        return self.base_url.startswith("https://")

    @property
    def mail_mode(self) -> str:
        return "smtp" if self.smtp_host else "console"


def load() -> Settings:
    s = Settings()
    if s.registration not in ("approval", "open", "invite"):
        s.registration = "approval"
    return s
