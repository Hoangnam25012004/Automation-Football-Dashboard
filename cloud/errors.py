"""Lỗi API của bản cloud: cùng dạng JSON với server.py — {"error": {"code", "message", "hint"}}."""
from __future__ import annotations

# mã → (HTTP status, thông điệp mặc định hiển thị trên UI)
CODES: dict[str, tuple[int, str]] = {
    "E_AUTH_REQUIRED": (401, "Please sign in."),
    "E_FORBIDDEN": (403, "You do not have permission to do that."),
    "E_CSRF": (403, "Your session expired. Reload the page and try again."),
    "E_BAD_REQUEST": (400, "The request is not valid."),
    "E_NOT_FOUND": (404, "Not found."),
    "E_JOB_NOT_FOUND": (404, "That request is no longer known to the server."),
    "E_MATCH_NOT_IN_LIBRARY": (404, "This match is not in the library."),
    "E_EMAIL_TAKEN": (409, "An account with this email already exists."),
    "E_WEAK_PASSWORD": (400, "Choose a stronger password."),
    "E_BAD_CREDENTIALS": (401, "Email or password is incorrect."),
    "E_ACCOUNT_PENDING": (403, "Your account is waiting for approval by an administrator."),
    "E_ACCOUNT_UNVERIFIED": (403, "Please confirm your email address first — check your inbox."),
    "E_ACCOUNT_DISABLED": (403, "This account has been disabled."),
    "E_TOKEN_INVALID": (400, "This link is invalid or has expired."),
    "E_REGISTRATION_CLOSED": (403, "Sign-up is closed. Ask an administrator for an invitation."),
    "E_QUOTA": (429, "You have reached your daily limit of new matches."),
    "E_SYSTEM_BUSY": (429, "The system is busy. Try again in a few minutes."),
    "E_RATE_LIMITED": (429, "Too many attempts. Wait a few minutes and try again."),
    "E_SOURCE_PAUSED": (503, "Reading new matches is paused because Flashscore refused our requests."),
    "E_REFRESH_TOO_SOON": (429, "This match was refreshed recently."),
    "E_MID_REQUIRED": (400, "The link must include the ?mid= part."),
    "E_PAYLOAD_TOO_LARGE": (413, "Request body is too large."),
}


class ApiError(Exception):
    def __init__(self, code: str, message: str | None = None, hint: str = "", status: int | None = None):
        default_status, default_message = CODES.get(code, (400, "Request failed."))
        self.code = code
        self.status = status or default_status
        self.message = message or default_message
        self.hint = hint
        super().__init__(f"{code}: {self.message}")

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "hint": self.hint}
