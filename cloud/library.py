"""Thư viện trận: lưu kết quả crawl, tìm kiếm, link chia sẻ (design doc cloud §6–§8)."""
from __future__ import annotations

import json
import sqlite3

from crawler.assemble import SCHEMA_VERSION

from .db import audit, iso
from .errors import ApiError
from .security import new_token

PAGE_SIZE = 20


def _summary_fields(result: dict) -> dict:
    stats = result.get("stats") or {}
    title = str(stats.get("matchTitle") or "")
    parts = [p.strip() for p in title.split(" vs ")] if " vs " in title else [stats.get("home", ""), stats.get("away", "")]
    fs = (result.get("summary") or {}).get("finalScore") or {}
    meta = result.get("meta") or {}
    score = f"{fs.get('h')}–{fs.get('a')}" if fs.get("h") is not None and fs.get("a") is not None else ""
    return {"home": parts[0][:80], "away": (parts[1] if len(parts) > 1 else "")[:80], "score": score,
            "competition": str(meta.get("competition") or "")[:120], "kickoff": str(meta.get("kickoff") or "")[:40]}


def find(conn: sqlite3.Connection, source: str, key: str):
    return conn.execute("SELECT * FROM matches WHERE source = ? AND match_key = ?", (source, key)).fetchone()


def latest_result(conn: sqlite3.Connection, match_id: int):
    return conn.execute("SELECT * FROM match_results WHERE match_id = ? ORDER BY id DESC LIMIT 1", (match_id,)).fetchone()


def is_current(conn: sqlite3.Connection, source: str, key: str) -> bool:
    """Trận có sẵn với schemaVersion hiện hành ⇒ phục vụ từ thư viện, không crawl lại."""
    m = find(conn, source, key)
    if not m:
        return False
    r = latest_result(conn, m["id"])
    return bool(r) and r["schema_version"] >= SCHEMA_VERSION


def store(conn: sqlite3.Connection, source: str, key: str, url: str, result: dict, user_id: int | None) -> int:
    """Ghi kết quả (gọi bên trong giao dịch của worker). Giữ tối đa 3 phiên bản/trận."""
    fields = _summary_fields(result)
    now = iso()
    existing = find(conn, source, key)
    if existing:
        match_id = existing["id"]
        conn.execute("UPDATE matches SET source_url = ?, home = ?, away = ?, score = ?, competition = ?, kickoff = ?, "
                     "refreshed_at = ? WHERE id = ?", (url, fields["home"], fields["away"], fields["score"],
                                                       fields["competition"], fields["kickoff"], now, match_id))
    else:
        match_id = conn.execute("INSERT INTO matches(source, match_key, source_url, home, away, score, competition, kickoff, "
                                "created_by, created_at, refreshed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (source, key, url, fields["home"], fields["away"], fields["score"], fields["competition"],
                                 fields["kickoff"], user_id, now, now)).lastrowid
    conn.execute("INSERT INTO match_results(match_id, schema_version, result_json, fetched_at) VALUES (?, ?, ?, ?)",
                 (match_id, int(result.get("schemaVersion") or 1), json.dumps(result, ensure_ascii=False), now))
    conn.execute("DELETE FROM match_results WHERE match_id = ? AND id NOT IN "
                 "(SELECT id FROM match_results WHERE match_id = ? ORDER BY id DESC LIMIT 3)", (match_id, match_id))
    return match_id


def get_result(conn: sqlite3.Connection, source: str, key: str) -> dict:
    m = find(conn, source, key)
    r = latest_result(conn, m["id"]) if m else None
    if not r:
        raise ApiError("E_MATCH_NOT_IN_LIBRARY")
    return json.loads(r["result_json"])


def entry(row, viewer=None) -> dict:
    can_manage = bool(viewer) and (viewer["role"] == "admin" or viewer["id"] == row["created_by"])
    return {"mid": row["match_key"], "source": row["source"], "home": row["home"], "away": row["away"],
            "score": row["score"], "competition": row["competition"], "kickoff": row["kickoff"],
            "createdAt": row["created_at"], "refreshedAt": row["refreshed_at"],
            "createdBy": row["creator"] if "creator" in row.keys() else None,
            "shared": bool(row["share_token"]) if can_manage else None,
            "shareToken": row["share_token"] if can_manage else None, "canManage": can_manage}


def search(conn: sqlite3.Connection, viewer, q: str = "", page: int = 1) -> dict:
    q = (q or "").strip()[:80]
    page = max(1, min(int(page or 1), 1000))
    where, args = "", []
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where = "WHERE m.home LIKE ? ESCAPE '\\' OR m.away LIKE ? ESCAPE '\\' OR m.competition LIKE ? ESCAPE '\\'"
        args = [like, like, like]
    total = conn.execute(f"SELECT COUNT(*) FROM matches m {where}", args).fetchone()[0]
    rows = conn.execute(f"SELECT m.*, u.email AS creator FROM matches m LEFT JOIN users u ON u.id = m.created_by {where} "
                        "ORDER BY m.refreshed_at DESC, m.id DESC LIMIT ? OFFSET ?", args + [PAGE_SIZE, (page - 1) * PAGE_SIZE]).fetchall()
    return {"items": [entry(r, viewer) for r in rows], "page": page, "pageSize": PAGE_SIZE, "total": total}


def _manageable(conn: sqlite3.Connection, user, source: str, key: str):
    m = find(conn, source, key)
    if not m:
        raise ApiError("E_MATCH_NOT_IN_LIBRARY")
    if user["role"] != "admin" and m["created_by"] != user["id"]:
        raise ApiError("E_FORBIDDEN")
    return m


def set_share(conn: sqlite3.Connection, user, source: str, key: str, enabled: bool) -> dict:
    m = _manageable(conn, user, source, key)
    token = new_token(24) if enabled else None
    conn.execute("UPDATE matches SET share_token = ? WHERE id = ?", (token, m["id"]))
    audit(conn, user["id"], "share_on" if enabled else "share_off", f"{source}:{key}")
    return {"shareToken": token}


def check_share(conn: sqlite3.Connection, source: str, key: str, token) -> bool:
    from .security import same
    m = find(conn, source, key)
    return bool(m and m["share_token"] and isinstance(token, str) and same(token, m["share_token"]))


def manageable(conn: sqlite3.Connection, user, source: str, key: str):
    return _manageable(conn, user, source, key)
