"""Hàng đợi job trong SQLite: khử trùng lặp theo trận, hạn mức, ngắt mạch nguồn dữ liệu (design doc cloud §8, §10).

Hình dạng JSON của job giữ đúng như server.py ({jobId, status, progress, result|error}) để trang báo cáo
(`Api.wait` — vùng đóng băng) dùng được mà không sửa.
"""
from __future__ import annotations

import json
import secrets
import sqlite3

from crawler.run import TOTAL_STEPS

from . import datasource, library, mail
from .config import Settings
from .db import audit, get_setting, iso, now_ts, set_setting, tx
from .errors import ApiError

STALE_RUNNING_S = 300          # job 'running' quá 5 phút mà worker không còn ⇒ coi như mất
MAX_ATTEMPTS = 2
BREAKER_PAUSE_S = 30 * 60
BREAKER_STRIKES = 2            # 2 lần E_BLOCKED liên tiếp ⇒ tạm dừng 30 phút
BREAKER_MANUAL_TRIPS = 3       # 3 lần tạm dừng trong 24 h ⇒ dừng tới khi admin mở lại


# ---------- ngắt mạch ----------
def breaker(conn: sqlite3.Connection) -> dict:
    state = get_setting(conn, "breaker", {}) or {}
    return {"pausedUntil": float(state.get("pausedUntil", 0)), "manual": bool(state.get("manual", False)),
            "strikes": int(state.get("strikes", 0)), "trips": [float(t) for t in state.get("trips", [])]}


def breaker_open(conn: sqlite3.Connection) -> bool:
    b = breaker(conn)
    return b["manual"] or b["pausedUntil"] > now_ts()


def record_source_result(conn: sqlite3.Connection, settings: Settings, blocked: bool) -> None:
    b = breaker(conn)
    if not blocked:
        if b["strikes"]:
            b["strikes"] = 0
            set_setting(conn, "breaker", b)
        return
    b["strikes"] += 1
    if b["strikes"] >= BREAKER_STRIKES:
        now = now_ts()
        b["strikes"], b["pausedUntil"] = 0, now + BREAKER_PAUSE_S
        b["trips"] = [t for t in b["trips"] if t > now - 86400] + [now]
        if len(b["trips"]) >= BREAKER_MANUAL_TRIPS:
            b["manual"] = True
        set_setting(conn, "breaker", b)
        audit(conn, None, "breaker_trip", "manual" if b["manual"] else "30 min")
        mail.alert_admin(settings, "Flashscore refused requests — crawling paused",
                         "Crawling new matches is paused " + ("until an administrator resumes it" if b["manual"]
                                                              else "for 30 minutes") + f". Admin page: {settings.base_url}/#/admin")
    else:
        set_setting(conn, "breaker", b)


def reset_breaker(conn: sqlite3.Connection, admin_id: int | None) -> dict:
    set_setting(conn, "breaker", {"pausedUntil": 0, "manual": False, "strikes": 0, "trips": []})
    audit(conn, admin_id, "breaker_reset")
    return breaker(conn)


# ---------- gửi / đọc job ----------
def _new_id() -> str:
    return secrets.token_hex(8)


def _queue_position(conn: sqlite3.Connection, job) -> int:
    ahead = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'queued' AND created_ts < ?", (job["created_ts"],)).fetchone()[0]
    running = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'running'").fetchone()[0]
    return ahead + running + 1


def user_quota(settings: Settings, user) -> int:
    return user["daily_crawl_quota"] if user["daily_crawl_quota"] is not None else settings.quota_user_daily


def used_today(conn: sqlite3.Connection, user_id: int) -> int:
    return conn.execute("SELECT COUNT(*) FROM jobs WHERE requested_by = ? AND cached = 0 AND created_ts > ?",
                        (user_id, now_ts() - 86400)).fetchone()[0]


def submit(conn: sqlite3.Connection, settings: Settings, user, url, force: bool = False) -> dict:
    """Dán link ⇒ phục vụ từ thư viện (không tốn hạn mức) | gộp vào job đang chạy | xếp hàng crawl mới."""
    if not isinstance(url, str):
        raise ApiError("E_BAD_REQUEST", "Send the link as JSON: {\"url\": \"…\"}.")
    ref = datasource.get().parse_ref(url.strip())
    now = now_ts()
    with tx(conn):
        if not force and library.is_current(conn, ref.source, ref.key):
            job_id = _new_id()
            conn.execute("INSERT INTO jobs(id, source, match_key, url, requested_by, cached, status, created_at, created_ts, "
                         "finished_at) VALUES (?, ?, ?, ?, ?, 1, 'done', ?, ?, ?)",
                         (job_id, ref.source, ref.key, ref.url, user["id"], iso(), now, iso()))
            return {"jobId": job_id, "status": "done", "mid": ref.key}
        active = conn.execute("SELECT * FROM jobs WHERE source = ? AND match_key = ? AND status IN ('queued', 'running')",
                              (ref.source, ref.key)).fetchone()
        if active:
            return {"jobId": active["id"], "status": active["status"], "mid": ref.key,
                    "position": _queue_position(conn, active) if active["status"] == "queued" else 0}
        if breaker_open(conn):
            raise ApiError("E_SOURCE_PAUSED", hint="Matches already in the library can still be opened.")
        if user["role"] != "admin" and used_today(conn, user["id"]) >= user_quota(settings, user):
            raise ApiError("E_QUOTA", hint="Matches already in the library do not count. The limit resets over 24 hours.")
        recent = conn.execute("SELECT COUNT(*) FROM jobs WHERE cached = 0 AND created_ts > ?", (now - 3600,)).fetchone()[0]
        queued = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'queued'").fetchone()[0]
        if recent >= settings.quota_global_hourly or queued >= settings.queue_max:
            raise ApiError("E_SYSTEM_BUSY")
        job_id = _new_id()
        conn.execute("INSERT INTO jobs(id, source, match_key, url, requested_by, status, progress_json, created_at, created_ts) "
                     "VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?)",
                     (job_id, ref.source, ref.key, ref.url, user["id"],
                      json.dumps({"phase": "queued", "done": 0, "total": TOTAL_STEPS, "message": "Waiting in the queue…"}),
                      iso(), now))
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        audit(conn, user["id"], "crawl_request" if not force else "crawl_refresh", f"{ref.source}:{ref.key}")
        return {"jobId": job_id, "status": "queued", "mid": ref.key, "position": _queue_position(conn, job)}


def get(conn: sqlite3.Connection, job_id: str) -> dict:
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        raise ApiError("E_JOB_NOT_FOUND", hint="Start again with Generate report.")
    data = {"jobId": job["id"], "status": job["status"], "mid": job["match_key"]}
    if job["status"] == "queued":
        position = _queue_position(conn, job)
        data["position"] = position
        data["progress"] = {"phase": "queued", "done": 0, "total": TOTAL_STEPS,
                            "message": f"Waiting in the queue (position {position})…"}
    else:
        data["progress"] = json.loads(job["progress_json"]) if job["progress_json"] else \
            {"phase": job["status"], "done": TOTAL_STEPS if job["status"] == "done" else 0, "total": TOTAL_STEPS,
             "message": "Done" if job["status"] == "done" else "Reading the match…"}
    if job["status"] == "done":
        result = library.get_result(conn, job["source"], job["match_key"])
        data["result"], data["warnings"] = result, result.get("warnings", [])
    if job["status"] == "error":
        data["error"] = json.loads(job["error_json"])
    return data


def refresh(conn: sqlite3.Connection, settings: Settings, user, source: str, key: str) -> dict:
    m = library.manageable(conn, user, source, key)
    from .db import parse_iso, utcnow
    age_h = (utcnow() - parse_iso(m["refreshed_at"])).total_seconds() / 3600
    if user["role"] != "admin" and age_h < settings.refresh_cooldown_h:
        raise ApiError("E_REFRESH_TOO_SOON", hint=f"A match can be refreshed once every {settings.refresh_cooldown_h} hours.")
    return submit(conn, settings, user, m["source_url"], force=True)


# ---------- phía worker ----------
def requeue_stale(conn: sqlite3.Connection) -> None:
    cutoff = now_ts() - STALE_RUNNING_S
    for job in conn.execute("SELECT * FROM jobs WHERE status = 'running' AND started_ts < ?", (cutoff,)).fetchall():
        if job["attempts"] < MAX_ATTEMPTS:
            conn.execute("UPDATE jobs SET status = 'queued', started_at = NULL, started_ts = NULL WHERE id = ?", (job["id"],))
        else:
            err = {"code": "E_INTERNAL", "message": "Unexpected error while reading the match.",
                   "hint": "The worker stopped while reading this match. Try again."}
            conn.execute("UPDATE jobs SET status = 'error', error_json = ?, finished_at = ? WHERE id = ?",
                         (json.dumps(err), iso(), job["id"]))


def claim(conn: sqlite3.Connection):
    with tx(conn):
        requeue_stale(conn)
        job = conn.execute("SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_ts LIMIT 1").fetchone()
        if not job:
            return None
        conn.execute("UPDATE jobs SET status = 'running', attempts = attempts + 1, started_at = ?, started_ts = ? WHERE id = ?",
                     (iso(), now_ts(), job["id"]))
        return conn.execute("SELECT * FROM jobs WHERE id = ?", (job["id"],)).fetchone()


def set_progress(conn: sqlite3.Connection, job_id: str, progress: dict) -> None:
    conn.execute("UPDATE jobs SET progress_json = ? WHERE id = ? AND status = 'running'", (json.dumps(progress), job_id))


def finish_ok(conn: sqlite3.Connection, job, result: dict) -> None:
    with tx(conn):
        library.store(conn, job["source"], job["match_key"], job["url"], result, job["requested_by"])
        conn.execute("UPDATE jobs SET status = 'done', finished_at = ?, progress_json = ? WHERE id = ?",
                     (iso(), json.dumps({"phase": "done", "done": TOTAL_STEPS, "total": TOTAL_STEPS, "message": "Done"}), job["id"]))


def finish_error(conn: sqlite3.Connection, job, error: dict) -> None:
    with tx(conn):
        conn.execute("UPDATE jobs SET status = 'error', error_json = ?, finished_at = ? WHERE id = ?",
                     (json.dumps(error), iso(), job["id"]))


def stats(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT SUM(status = 'queued') AS queued, SUM(status = 'running') AS running FROM jobs").fetchone()
    return {"queued": row["queued"] or 0, "running": row["running"] or 0}
