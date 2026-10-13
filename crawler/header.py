"""Header của trận: tên đội, ngày giờ, tỉ số, trạng thái, logo (design doc §6.3)."""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .errors import CrawlError

JS_HEADER = r"""() => {
  const T = s => { const e = document.querySelector(s); return e ? (e.innerText || '').replace(/\s+/g, ' ').trim() : ''; };
  const A = (s, a) => { const e = document.querySelector(s); return e ? (e.getAttribute(a) || '') : ''; };
  return {
    home: T('.duelParticipant__home .participant__participantName'),
    away: T('.duelParticipant__away .participant__participantName'),
    start: T('.duelParticipant__startTime'),
    score: T('.detailScore__wrapper'),
    status: T('.detailScore__status'),
    homeLogo: A('.duelParticipant__home img.participant__image', 'src'),
    awayLogo: A('.duelParticipant__away img.participant__image', 'src'),
  };
}"""

# Trạng thái coi là "đã kết thúc". Đã thấy trên trang thật (10/2026): "Finished", "After Extra Time",
# "After 90 minutes" (luân lưu ngay sau 90 phút, vd EFL Cup); các dạng còn lại là phòng hờ.
FINISHED = re.compile(r"^(finished|after extra time|after penalties|after (90|120) minutes|aet|ap|after pen\.?)$",
                      re.IGNORECASE)


@dataclass
class MatchInfo:
    home: str
    away: str
    start: str
    score_home: int | None
    score_away: int | None
    status: str
    home_logo_url: str
    away_logo_url: str


def read_header(page) -> MatchInfo:
    try:
        page.wait_for_selector(".duelParticipant .participant__participantName", timeout=15_000)
    except PlaywrightTimeout:
        raise CrawlError("E_MATCH_NOT_FOUND") from None
    try:
        page.wait_for_selector(".detailScore__status", state="attached", timeout=5_000)
    except PlaywrightTimeout:
        pass                                  # trận chưa đá có thể không có ô trạng thái
    raw = page.evaluate(JS_HEADER)
    if not raw["status"]:                     # ô trạng thái đôi khi được điền chậm hơn tên đội
        page.wait_for_timeout(800)
        raw = page.evaluate(JS_HEADER)
    if not raw["home"] or not raw["away"]:
        raise CrawlError("E_MATCH_NOT_FOUND")
    m = re.search(r"(\d+)\D+(\d+)", raw["score"])
    info = MatchInfo(
        home=raw["home"], away=raw["away"], start=raw["start"],
        score_home=int(m.group(1)) if m else None, score_away=int(m.group(2)) if m else None,
        status=raw["status"], home_logo_url=raw["homeLogo"], away_logo_url=raw["awayLogo"],
    )
    if not FINISHED.match(info.status.strip()):
        shown = info.status.strip() or "not started"
        raise CrawlError("E_MATCH_NOT_FINISHED", hint=f"Flashscore shows the status “{shown}”. Try again after full time.")
    return info


def logo_name(url: str) -> str:
    """Tên file logo (vd "SlUDTKeM-d29rUy0U.png") — dùng để so logo giữa các khối của trang."""
    return url.rsplit("/", 1)[-1] if url else ""


def fetch_data_url(ctx, url: str) -> str | None:
    """Tải ảnh qua ctx.request (không bị chặn bởi route) → data URL. Chỉ tải từ *.flashscore.com."""
    if not url:
        return None
    if url.startswith("//"):
        url = "https:" + url
    host = (urlsplit(url).hostname or "").lower()
    if not url.startswith("https://") or not (host == "flashscore.com" or host.endswith(".flashscore.com")):
        return None
    try:
        response = ctx.request.get(url, timeout=10_000)
        if not response.ok:
            return None
        mime = (response.headers.get("content-type") or "image/png").split(";")[0].strip()
        if not mime.startswith("image/"):
            return None
        return f"data:{mime};base64," + base64.b64encode(response.body()).decode("ascii")
    except PlaywrightError:
        return None
