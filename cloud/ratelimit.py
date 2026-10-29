"""Giới hạn tốc độ theo cửa sổ trượt, lưu trong SQLite (sống sót qua khởi động lại, dùng chung giữa các tiến trình)."""
from __future__ import annotations

import sqlite3

from .db import now_ts


def count(conn: sqlite3.Connection, bucket: str, key: str, window_s: float) -> int:
    return conn.execute("SELECT COUNT(*) FROM rate_events WHERE bucket = ? AND key = ? AND ts > ?",
                        (bucket, key, now_ts() - window_s)).fetchone()[0]


def hit(conn: sqlite3.Connection, bucket: str, key: str, limit: int, window_s: float) -> bool:
    """Ghi 1 sự kiện nếu còn trong hạn mức. → True nếu được phép."""
    if count(conn, bucket, key, window_s) >= limit:
        return False
    conn.execute("INSERT INTO rate_events(bucket, key, ts) VALUES (?, ?, ?)", (bucket, key, now_ts()))
    return True


def clear(conn: sqlite3.Connection, bucket: str, key: str) -> None:
    conn.execute("DELETE FROM rate_events WHERE bucket = ? AND key = ?", (bucket, key))


def prune(conn: sqlite3.Connection, older_than_s: float = 2 * 86400) -> None:
    conn.execute("DELETE FROM rate_events WHERE ts < ?", (now_ts() - older_than_s,))
