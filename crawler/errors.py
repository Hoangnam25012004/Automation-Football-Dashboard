"""Mã lỗi và cảnh báo của crawler (design doc §4.3).

Thông điệp hiển thị trên giao diện (tiếng Anh, như phần còn lại của web); log console dùng tiếng Việt.
"""
from __future__ import annotations

# mã → (HTTP status, thông điệp, gợi ý)
ERRORS: dict[str, tuple[int, str, str]] = {
    "E_URL_INVALID": (400, "That is not a Flashscore football match link.",
                      "Paste a link like https://www.flashscore.com/match/football/<home>/<away>/?mid=<id>"),
    "E_BUSY": (429, "Another match is being read right now.", "Wait for it to finish, then try again."),
    "E_MATCH_NOT_FOUND": (404, "Flashscore has no match at that link.", "Copy the link again from the match page."),
    "E_MATCH_NOT_FINISHED": (422, "This match has not finished yet.", "Try again after full time."),
    "E_NO_PLAYER_STATS": (422, "Flashscore has no player stats for this match.",
                          "The dashboard needs player stats; many lower-tier competitions do not have them."),
    "E_NETWORK": (502, "Could not reach flashscore.com.", "Check your internet connection and try again."),
    "E_BLOCKED": (502, "Flashscore refused the request.", "Wait a few minutes, then try again."),
    "E_TIMEOUT": (504, "Reading the match took too long.", "Try again — Flashscore may be slow right now."),
    "E_INTERNAL": (500, "Unexpected error while reading the match.",
                   "See the server window for details (set FS_DEBUG=1 to save the page HTML)."),
}

WARNINGS: dict[str, str] = {
    "W_NO_MID": "The link has no ?mid= part, so Flashscore picked the match itself — check the teams and date.",
    "W_TIMELINE_EMPTY": "The match timeline could not be read.",
    "W_TIMELINE_SCORE_MISMATCH": "The goals in the timeline do not add up to the final score.",
    "W_SCORE_MISMATCH": "The goals in the player stats do not add up to the final score.",
    "W_NO_LINEUPS": "Line-ups are not available for this match.",
    "W_LINEUPS_PARTIAL": "The line-ups look incomplete.",
    "W_NO_FORMATION": "No formation diagram is available for this match.",
    "W_ROSTER_MISMATCH": "Some starting players are missing from the player stats.",
    "W_TEAM_ORDER_SWAPPED": "Home/away order in the player stats was corrected automatically.",
    "W_TEAM_CODE_COLLISION": "Both teams use the same short code; HOME/AWAY are used internally.",
    "W_STATS_TAB_EMPTY": "Some player-stats tabs could not be read.",
    "W_NO_TEAM_STATS": "Team statistics are not available for this match; team totals are derived from player stats.",
}


class CrawlError(Exception):
    """Lỗi dừng job; mang mã, HTTP status và thông điệp cho giao diện."""

    def __init__(self, code: str, message: str | None = None, hint: str | None = None):
        status, default_message, default_hint = ERRORS[code]
        self.code = code
        self.status = status
        self.message = message or default_message
        self.hint = default_hint if hint is None else hint
        super().__init__(f"{code}: {self.message}")

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "hint": self.hint}


class Warnings:
    """Danh sách cảnh báo không chặn kết quả (giữ thứ tự, không trùng lặp)."""

    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, code: str, detail: str = "") -> None:
        if any(w["code"] == code for w in self.items):
            if detail:
                for w in self.items:
                    if w["code"] == code and detail not in w.get("detail", ""):
                        w["detail"] = (w.get("detail", "") + "; " + detail).strip("; ")
            return
        item = {"code": code, "message": WARNINGS[code]}
        if detail:
            item["detail"] = detail
        self.items.append(item)

    def codes(self) -> list[str]:
        return [w["code"] for w in self.items]
