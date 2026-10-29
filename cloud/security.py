"""Mật khẩu (scrypt, stdlib) và token ngẫu nhiên. Không log mật khẩu/token ở bất cứ đâu."""
from __future__ import annotations

import hashlib
import hmac
import secrets

# scrypt: n=2^14, r=8, p=1 ⇒ ~16 MB RAM/lần băm (design doc cloud §5.2)
_N, _R, _P, _DKLEN = 2 ** 14, 8, 1, 32
MIN_PASSWORD = 10
# Mật khẩu phổ biến nhất (rút gọn) — chặn những lựa chọn bị đoán đầu tiên
_COMMON = {
    "password", "password1", "password12", "password123", "1234567890", "12345678910", "qwertyuiop", "qwerty1234",
    "1q2w3e4r5t", "iloveyou12", "football123", "football12", "abcdefghij", "0123456789", "1111111111", "aaaaaaaaaa",
    "letmein123", "welcome123", "admin12345", "passw0rd12", "matchperformance", "flashscore", "123456789a",
    "zxcvbnm123", "princess12", "sunshine12", "liverpool1", "manchester", "arsenal123", "chelsea123",
}


def hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return digest, salt


def verify_password(password: str, digest: bytes, salt: bytes) -> bool:
    candidate, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate, digest)


def password_problem(password: str, email: str = "") -> str | None:
    """→ lý do (tiếng Anh, hiển thị trên UI) nếu mật khẩu yếu, None nếu đạt."""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        return f"Use at least {MIN_PASSWORD} characters."
    if len(password) > 200:
        return "Use at most 200 characters."
    lowered = password.lower()
    if lowered in _COMMON or len(set(lowered)) <= 2:
        return "This password is too common."
    local = email.split("@")[0].lower() if email else ""
    if local and len(local) >= 4 and local in lowered:
        return "Do not use your email name in the password."
    return None


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def same(a: str, b: str) -> bool:
    return hmac.compare_digest((a or "").encode("utf-8"), (b or "").encode("utf-8"))
