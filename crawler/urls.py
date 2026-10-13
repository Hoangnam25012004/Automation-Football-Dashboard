"""Phân tích và chuẩn hoá link trận Flashscore (design doc §6.1).

Link luôn được DỰNG LẠI từ các thành phần đã kiểm tra — không bao giờ dùng nguyên văn
chuỗi người dùng dán vào (chống SSRF). Tham số `?mid=` được giữ lại vì nó xác định đúng trận.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from .errors import CrawlError

HOST = "www.flashscore.com"
_ALLOWED_HOSTS = {"www.flashscore.com", "flashscore.com"}
_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,119}$")   # vd "johor-dt-AVV6BGlb"
_MID = re.compile(r"^[A-Za-z0-9]{6,12}$")                       # vd "vLuGlk0n"


@dataclass(frozen=True)
class MatchRef:
    # Hai đoạn đường dẫn đội, vd "johor-dt-AVV6BGlb". Thứ tự trong URL KHÔNG phải nhà/khách
    # (đã thấy "alaves…/ath-bilbao…" cho trận Athletic Bilbao v Alaves) — nhà/khách lấy từ header.
    team1: str
    team2: str
    mid: str | None      # id trận trong ?mid=, có thể thiếu

    @property
    def base(self) -> str:
        return f"https://{HOST}/match/football/{self.team1}/{self.team2}/"

    def url(self, path: str = "") -> str:
        """URL trang con (vd "summary/lineups"), luôn kèm ?mid= nếu có."""
        path = path.strip("/")
        url = self.base + (path + "/" if path else "")
        return url + (f"?mid={self.mid}" if self.mid else "")


def parse_match_url(raw: str) -> MatchRef:
    text = (raw or "").strip()
    if not text:
        raise CrawlError("E_URL_INVALID", "Paste a Flashscore match link first.")
    if len(text) > 500 or any(c.isspace() for c in text):
        raise CrawlError("E_URL_INVALID")
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        raise CrawlError("E_URL_INVALID") from None
    if parts.scheme.lower() != "https" or (parts.hostname or "").lower() not in _ALLOWED_HOSTS:
        raise CrawlError("E_URL_INVALID")
    if parts.username or parts.password or port not in (None, 443):
        raise CrawlError("E_URL_INVALID")
    segments = [s for s in parts.path.split("/") if s]
    if len(segments) < 4 or segments[0].lower() != "match":
        raise CrawlError("E_URL_INVALID")
    if segments[1].lower() != "football":
        raise CrawlError("E_URL_INVALID", "Only football matches are supported.")
    team1, team2 = segments[2], segments[3]
    if not (_SEGMENT.match(team1) and _SEGMENT.match(team2)):
        raise CrawlError("E_URL_INVALID")
    mids = parse_qs(parts.query).get("mid", [])
    mid = mids[0] if mids else None
    if mid is not None and not _MID.match(mid):
        raise CrawlError("E_URL_INVALID", "The ?mid= part of the link looks damaged.")
    return MatchRef(team1, team2, mid)
