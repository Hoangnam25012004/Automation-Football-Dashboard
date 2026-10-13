"""Chromium headless, chặn tài nguyên nặng, xử lý banner cookie (design doc §6.2)."""
from __future__ import annotations

import os
import re

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .errors import CrawlError

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")          # cùng UA với các script legacy
DESKTOP = {"width": 1280, "height": 900}
NARROW = {"width": 420, "height": 900}            # ≤ ~760 px ⇒ sân Formation dọc, đội nhà ở trên
NAV_TIMEOUT_MS = 30_000
SELECTOR_TIMEOUT_MS = 15_000

_BLOCKED_TYPES = {"image", "font", "media"}
_BLOCKED_URL = re.compile(r"/ads/|/analytics/|/gtm/|doubleclick\.net|googlesyndication\.com|"
                          r"google-analytics\.com|googletagmanager\.com|adservice\.google")
_CONSENT_BUTTONS = ("#onetrust-reject-all-handler", "#onetrust-accept-btn-handler")
_HIDE_CONSENT_CSS = "#onetrust-consent-sdk{display:none !important}"
_HIDE_CONSENT_INIT = ("document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');"
                      f"s.textContent='{_HIDE_CONSENT_CSS}';document.head.appendChild(s);}});")


def parallel() -> int:
    """Số trang tải song song (FS_PARALLEL, mặc định 3; 1 = tuần tự như trước)."""
    try:
        return max(1, min(7, int(os.environ.get("FS_PARALLEL", "3"))))
    except ValueError:
        return 3


def headless() -> bool:
    return os.environ.get("FS_HEADLESS", "1") != "0"


def launch(playwright):
    return playwright.chromium.launch(headless=headless())


def _route(route) -> None:
    request = route.request
    if request.resource_type in _BLOCKED_TYPES or _BLOCKED_URL.search(request.url):
        route.abort()
    else:
        route.continue_()


def new_context(browser):
    ctx = browser.new_context(user_agent=UA, locale="en-GB", viewport=DESKTOP)
    ctx.set_default_navigation_timeout(NAV_TIMEOUT_MS)
    ctx.set_default_timeout(SELECTOR_TIMEOUT_MS)
    ctx.route("**/*", _route)       # ctx.request.get (tải logo) không đi qua route này
    return ctx


def goto(page, url: str, retries: int = 1, wait_until: str = "domcontentloaded"):
    """Điều hướng có 1 lần thử lại. Trả về Response; ném CrawlError cho mạng / bị chặn / quá giờ."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = page.goto(url, wait_until=wait_until)
        except PlaywrightTimeout as exc:
            last = exc
            continue
        except PlaywrightError as exc:
            last = exc
            if "net::ERR_" in str(exc) and attempt == retries:
                raise CrawlError("E_NETWORK") from exc
            continue
        if response is not None and response.status in (403, 429):
            raise CrawlError("E_BLOCKED", hint=f"Flashscore answered HTTP {response.status}. Wait a few minutes, then try again.")
        return response
    raise CrawlError("E_TIMEOUT") from last


def dismiss_consent(page, ctx, wait_ms: int = 6000) -> str:
    """Bấm "Reject all" (dự phòng "Accept") trên banner OneTrust ở trang đầu tiên của context.

    Banner hiện sau ~1 s và chặn mọi cú click nếu không xử lý. Không chờ bằng is_visible()
    vì hàm này không chờ. Sau đó, các trang tiếp theo của context được ẩn banner bằng CSS
    (lưới an toàn; quyết định Reject đã được lưu trong cookie).
    """
    used = "hidden"
    try:
        page.locator(", ".join(_CONSENT_BUTTONS)).first.wait_for(state="visible", timeout=wait_ms)
        for selector in _CONSENT_BUTTONS:
            button = page.locator(selector).first
            if button.is_visible():
                button.click(timeout=3000)
                used = selector
                break
        try:
            page.locator("#onetrust-banner-sdk").first.wait_for(state="hidden", timeout=3000)
        except PlaywrightTimeout:
            page.add_style_tag(content=_HIDE_CONSENT_CSS)
    except PlaywrightTimeout:
        page.add_style_tag(content=_HIDE_CONSENT_CSS)
    ctx.add_init_script(_HIDE_CONSENT_INIT)
    return used
