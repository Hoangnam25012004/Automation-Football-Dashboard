"""Tài khoản và phiên đăng nhập (design doc cloud §9). Logic thuần — không phụ thuộc FastAPI.

Trạng thái tài khoản:
  pending + email chưa xác minh → xác minh email → (REGISTRATION=open: active | approval: chờ admin duyệt → active)
  active ↔ disabled (admin)
"""
from __future__ import annotations

import re
import sqlite3

from . import mail, ratelimit
from .config import Settings
from .db import audit, get_setting, iso, iso_in, tx
from .errors import ApiError
from .security import hash_password, new_token, password_problem, token_hash, verify_password

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,63}$")
VERIFY_HOURS, RESET_MINUTES = 24, 30
SESSION_COOKIE, CSRF_COOKIE = "fs_session", "fs_csrf"
_DUMMY_HASH = hash_password("timing-equaliser-not-a-password")   # cùng thời gian khi email không tồn tại


def registration_mode(conn: sqlite3.Connection, settings: Settings) -> str:
    mode = get_setting(conn, "registration", settings.registration)
    return mode if mode in ("approval", "open", "invite") else "approval"


def _clean_email(email) -> str:
    email = (email or "").strip() if isinstance(email, str) else ""
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise ApiError("E_BAD_REQUEST", "Enter a valid email address.")
    return email


def _issue_token(conn: sqlite3.Connection, user_id: int, purpose: str, **ttl) -> str:
    token = new_token()
    conn.execute("UPDATE email_tokens SET used_at = ? WHERE user_id = ? AND purpose = ? AND used_at IS NULL",
                 (iso(), user_id, purpose))                       # chỉ link mới nhất còn hiệu lực
    conn.execute("INSERT INTO email_tokens(token_hash, user_id, purpose, expires_at) VALUES (?, ?, ?, ?)",
                 (token_hash(token), user_id, purpose, iso_in(**ttl)))
    return token


def _consume_token(conn: sqlite3.Connection, token, purpose: str) -> int:
    if not isinstance(token, str) or not 20 <= len(token) <= 100:
        raise ApiError("E_TOKEN_INVALID")
    row = conn.execute("SELECT user_id FROM email_tokens WHERE token_hash = ? AND purpose = ? AND used_at IS NULL "
                       "AND expires_at > ?", (token_hash(token), purpose, iso())).fetchone()
    if not row:
        raise ApiError("E_TOKEN_INVALID")
    conn.execute("UPDATE email_tokens SET used_at = ? WHERE token_hash = ?", (iso(), token_hash(token)))
    return row["user_id"]


# ---------- đăng ký / xác minh ----------
def register(conn: sqlite3.Connection, settings: Settings, email, password, ip: str) -> dict:
    mode = registration_mode(conn, settings)
    if mode == "invite":
        raise ApiError("E_REGISTRATION_CLOSED")
    email = _clean_email(email)
    problem = password_problem(password, email)
    if problem:
        raise ApiError("E_WEAK_PASSWORD", hint=problem)
    with tx(conn):
        if not ratelimit.hit(conn, "register", ip, 3, 3600):
            raise ApiError("E_RATE_LIMITED")
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if not existing:
            digest, salt = hash_password(password)
            cur = conn.execute("INSERT INTO users(email, pw_hash, pw_salt, created_at) VALUES (?, ?, ?, ?)",
                               (email, digest, salt, iso()))
            token = _issue_token(conn, cur.lastrowid, "verify", hours=VERIFY_HOURS)
            audit(conn, cur.lastrowid, "register")
    if existing:
        # không tiết lộ email đã có tài khoản: trả cùng một phản hồi, báo cho chủ email biết
        mail.send(settings, email, "Match Performance — sign-up attempt",
                  "Someone (maybe you) tried to create an account with this email, but you already have one.\n"
                  f"Sign in at {settings.base_url}/#/login or reset your password at {settings.base_url}/#/forgot.")
        return {"ok": True}
    mail.send(settings, email, "Match Performance — confirm your email",
              f"Confirm your email to finish creating your account:\n{settings.base_url}/#/verify/{token}\n\n"
              f"The link expires in {VERIFY_HOURS} hours. If you did not sign up, ignore this email.")
    return {"ok": True}


def verify_email(conn: sqlite3.Connection, settings: Settings, token) -> dict:
    mode = registration_mode(conn, settings)
    with tx(conn):
        user_id = _consume_token(conn, token, "verify")
        conn.execute("UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?) WHERE id = ?", (iso(), user_id))
        if mode == "open":
            conn.execute("UPDATE users SET status = 'active' WHERE id = ? AND status = 'pending'", (user_id,))
        row = conn.execute("SELECT email, status FROM users WHERE id = ?", (user_id,)).fetchone()
        audit(conn, user_id, "verify_email")
    if row["status"] == "pending":
        mail.alert_admin(settings, "New account waiting for approval",
                         f"A new account is waiting for approval. Review it at {settings.base_url}/#/admin")
    return {"ok": True, "status": row["status"]}


# ---------- đăng nhập / phiên ----------
def login(conn: sqlite3.Connection, settings: Settings, email, password, ip: str, ua: str) -> tuple[str, dict]:
    if not isinstance(email, str) or not isinstance(password, str) or len(password) > 200:
        raise ApiError("E_BAD_CREDENTIALS")
    key = email.strip().lower()[:254] + "|" + ip
    with tx(conn):
        if not ratelimit.hit(conn, "login", key, 5, 900) or not ratelimit.hit(conn, "login-ip", ip, 30, 900):
            raise ApiError("E_RATE_LIMITED")
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip(),)).fetchone()
    if user is None:
        verify_password(password, *_DUMMY_HASH)
        raise ApiError("E_BAD_CREDENTIALS")
    if not verify_password(password, user["pw_hash"], user["pw_salt"]):
        raise ApiError("E_BAD_CREDENTIALS")
    if user["status"] == "disabled":
        raise ApiError("E_ACCOUNT_DISABLED")
    if not user["email_verified_at"]:
        raise ApiError("E_ACCOUNT_UNVERIFIED")
    if user["status"] != "active":
        raise ApiError("E_ACCOUNT_PENDING")
    token, csrf = new_token(), new_token(24)
    with tx(conn):
        ratelimit.clear(conn, "login", key)
        conn.execute("INSERT INTO sessions(id, user_id, csrf, created_at, expires_at, ip, ua) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (token_hash(token), user["id"], csrf, iso(), iso_in(days=settings.session_days), ip, (ua or "")[:200]))
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (iso(), user["id"]))
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (iso(),))
        audit(conn, user["id"], "login")
    return token, {"csrf": csrf, "user": public_user(user)}


def session_user(conn: sqlite3.Connection, token) -> dict | None:
    """→ {"session_id", "csrf", "user": row} cho phiên còn hạn của tài khoản đang hoạt động."""
    if not isinstance(token, str) or not 20 <= len(token) <= 100:
        return None
    row = conn.execute("SELECT s.id AS sid, s.csrf, u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                       "WHERE s.id = ? AND s.expires_at > ? AND u.status = 'active'", (token_hash(token), iso())).fetchone()
    if not row:
        return None
    return {"session_id": row["sid"], "csrf": row["csrf"], "user": row}


def logout(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def public_user(row) -> dict:
    return {"id": row["id"], "email": row["email"], "role": row["role"], "status": row["status"],
            "verified": bool(row["email_verified_at"]), "createdAt": row["created_at"],
            "lastLoginAt": row["last_login_at"], "dailyQuota": row["daily_crawl_quota"]}


# ---------- quên / đặt lại mật khẩu ----------
def forgot(conn: sqlite3.Connection, settings: Settings, email, ip: str) -> dict:
    try:
        email = _clean_email(email)
    except ApiError:
        return {"ok": True}
    with tx(conn):
        if not ratelimit.hit(conn, "forgot", ip, 5, 3600):
            raise ApiError("E_RATE_LIMITED")
        user = conn.execute("SELECT id, status FROM users WHERE email = ?", (email,)).fetchone()
        token = _issue_token(conn, user["id"], "reset", minutes=RESET_MINUTES) if user and user["status"] != "disabled" else None
    if token:
        mail.send(settings, email, "Match Performance — reset your password",
                  f"Set a new password:\n{settings.base_url}/#/reset/{token}\n\n"
                  f"The link expires in {RESET_MINUTES} minutes and works once. If you did not ask for this, ignore this email.")
    return {"ok": True}                           # luôn cùng một phản hồi (không lộ email nào có tài khoản)


def reset_password(conn: sqlite3.Connection, token, password) -> dict:
    with tx(conn):
        user_id = _consume_token(conn, token, "reset")
        email = conn.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()["email"]
        problem = password_problem(password, email)
        if problem:
            raise ApiError("E_WEAK_PASSWORD", hint=problem)
        digest, salt = hash_password(password)
        # đặt lại mật khẩu qua email cũng chứng minh sở hữu email
        conn.execute("UPDATE users SET pw_hash = ?, pw_salt = ?, email_verified_at = COALESCE(email_verified_at, ?) "
                     "WHERE id = ?", (digest, salt, iso(), user_id))
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))       # đăng xuất mọi thiết bị
        audit(conn, user_id, "reset_password")
    return {"ok": True}


# ---------- xoá tài khoản (dữ liệu cá nhân — F8) ----------
def delete_account(conn: sqlite3.Connection, user, password) -> None:
    if not isinstance(password, str) or not verify_password(password, user["pw_hash"], user["pw_salt"]):
        raise ApiError("E_BAD_CREDENTIALS")
    with tx(conn):
        if user["role"] == "admin" and _active_admins(conn) <= 1:
            raise ApiError("E_FORBIDDEN", "You are the last administrator. Promote someone else first.")
        conn.execute("DELETE FROM users WHERE id = ?", (user["id"],))     # sessions/tokens xoá theo FK CASCADE
        audit(conn, None, "delete_account", f"user {user['id']}")


# ---------- quản trị ----------
def _active_admins(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND status = 'active'").fetchone()[0]


def list_users(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM users ORDER BY (status = 'pending' AND email_verified_at IS NOT NULL) DESC, "
                        "created_at DESC LIMIT 500").fetchall()
    return [public_user(r) for r in rows]


def admin_update_user(conn: sqlite3.Connection, settings: Settings, admin, user_id: int, changes: dict) -> dict:
    allowed = {"status": ("active", "disabled", "pending"), "role": ("admin", "member")}
    with tx(conn):
        target = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not target:
            raise ApiError("E_NOT_FOUND")
        for field in ("status", "role"):
            if field in changes and changes[field] not in allowed[field]:
                raise ApiError("E_BAD_REQUEST", f"Invalid {field}.")
        if target["id"] == admin["id"] and (changes.get("status", "active") != "active" or changes.get("role", "admin") != "admin"):
            raise ApiError("E_FORBIDDEN", "You cannot disable or demote yourself.")
        if "status" in changes:
            if changes["status"] == "active" and not target["email_verified_at"]:
                raise ApiError("E_BAD_REQUEST", "This user has not confirmed their email yet.")
            conn.execute("UPDATE users SET status = ? WHERE id = ?", (changes["status"], user_id))
            if changes["status"] != "active":
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        if "role" in changes:
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (changes["role"], user_id))
        if "dailyQuota" in changes:
            q = changes["dailyQuota"]
            if q is not None and (not isinstance(q, int) or isinstance(q, bool) or not 0 <= q <= 1000):
                raise ApiError("E_BAD_REQUEST", "Quota must be a number from 0 to 1000, or empty for the default.")
            conn.execute("UPDATE users SET daily_crawl_quota = ? WHERE id = ?", (q, user_id))
        audit(conn, admin["id"], "admin_update_user", f"user {user_id}: {sorted(changes)}")
        updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if target["status"] != "active" and updated["status"] == "active":
        mail.send(settings, updated["email"], "Match Performance — your account is ready",
                  f"Your account has been approved. Sign in at {settings.base_url}/#/login")
    return public_user(updated)


def admin_create_user(conn: sqlite3.Connection, settings: Settings, admin, email, role: str = "member") -> dict:
    """Mời người dùng (cả khi REGISTRATION=invite): tạo tài khoản active, gửi link đặt mật khẩu."""
    email = _clean_email(email)
    if role not in ("admin", "member"):
        raise ApiError("E_BAD_REQUEST", "Invalid role.")
    digest, salt = hash_password(new_token())     # mật khẩu ngẫu nhiên không ai biết; người dùng tự đặt qua link
    with tx(conn):
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise ApiError("E_EMAIL_TAKEN")
        cur = conn.execute("INSERT INTO users(email, pw_hash, pw_salt, role, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
                           (email, digest, salt, role, iso()))
        token = _issue_token(conn, cur.lastrowid, "reset", hours=VERIFY_HOURS)
        audit(conn, admin["id"] if admin else None, "admin_create_user", f"user {cur.lastrowid}")
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    mail.send(settings, email, "Match Performance — you have been invited",
              f"An administrator created an account for you. Set your password here:\n"
              f"{settings.base_url}/#/reset/{token}\n\nThe link expires in {VERIFY_HOURS} hours.")
    return public_user(row)


def create_admin(conn: sqlite3.Connection, email: str, password: str) -> int:
    """Dùng từ CLI (`python -m cloud.admin create-admin`) — tài khoản admin đầu tiên, đã kích hoạt."""
    email = _clean_email(email)
    problem = password_problem(password, email)
    if problem:
        raise ApiError("E_WEAK_PASSWORD", hint=problem)
    digest, salt = hash_password(password)
    with tx(conn):
        row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if row:
            conn.execute("UPDATE users SET pw_hash = ?, pw_salt = ?, role = 'admin', status = 'active', "
                         "email_verified_at = COALESCE(email_verified_at, ?) WHERE id = ?", (digest, salt, iso(), row["id"]))
            user_id = row["id"]
        else:
            user_id = conn.execute("INSERT INTO users(email, pw_hash, pw_salt, role, status, email_verified_at, created_at) "
                                   "VALUES (?, ?, ?, 'admin', 'active', ?, ?)", (email, digest, salt, iso(), iso())).lastrowid
        audit(conn, user_id, "create_admin_cli")
    return user_id
