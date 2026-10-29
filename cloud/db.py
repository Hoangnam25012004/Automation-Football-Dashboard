"""SQLite (WAL): kết nối, migration, giao dịch, tiện ích thời gian."""
from __future__ import annotations

import contextlib
import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime | None = None) -> str:
    return (dt or utcnow()).isoformat().replace("+00:00", "Z")


def iso_in(**delta) -> str:
    return iso(utcnow() + timedelta(**delta))


def parse_iso(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def connect(path: Path | str) -> sqlite3.Connection:
    """Mỗi request/worker một kết nối. autocommit (isolation_level=None) + giao dịch tường minh qua `tx()`."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextlib.contextmanager
def tx(conn: sqlite3.Connection):
    """BEGIN IMMEDIATE: khoá ghi ngay từ đầu ⇒ không có cảnh hai giao dịch cùng đọc rồi cùng ghi."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Áp các file migrations/NNN_*.sql chưa chạy (theo thứ tự tên). Trả về danh sách vừa áp."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
    applied = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.stem in done:
            continue
        sql = path.read_text(encoding="utf-8")
        conn.executescript("BEGIN IMMEDIATE;\n" + sql + "\nINSERT INTO schema_migrations VALUES ('"
                           + path.stem + "', '" + iso() + "');\nCOMMIT;")
        applied.append(path.stem)
    return applied


# ---------- settings (key/value) ----------
def get_setting(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_setting(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (key, json.dumps(value)))


def audit(conn: sqlite3.Connection, user_id: int | None, action: str, detail: str = "") -> None:
    conn.execute("INSERT INTO audit_log(at, user_id, action, detail) VALUES (?, ?, ?, ?)",
                 (iso(), user_id, action, detail[:500]))


def now_ts() -> float:
    return time.time()
