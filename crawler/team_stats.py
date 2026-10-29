"""Team stats cấp đội: tab STATS của trận, 3 phạm vi Overall / 1st half / 2nd half
(design doc dashboard-redesign §3.2). Dữ liệu MỀM: lỗi ⇒ cảnh báo W_NO_TEAM_STATS, không dừng job.
"""
from __future__ import annotations

import re
import time

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .browser import goto
from .errors import CrawlError

# (slug trong URL, khoá trong result.teamStats)
SCOPES = [("overall", "overall"), ("1st-half", "firstHalf"), ("2nd-half", "secondHalf")]

# Mỗi hàng: [data-testid="wcl-statistics"]; tiêu đề nhóm: [data-testid="wcl-headerSection-text"].
# Giá trị nằm trong [class*="wcl-value_"] (đội khách bọc trong [class*="wcl-awayValue_"]); tỉ lệ "(81%)"
# là [data-testid="wcl-caption-05"] bên trong ô giá trị. Dùng textContent để không dính text-transform CSS.
JS_TEAM_STATS = r"""() => {
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const cell = el => {
    if (!el) return { v: '', pct: '' };
    const c = el.cloneNode(true);
    const cap = c.querySelector('[data-testid="wcl-caption-05"]');
    const pct = cap ? clean(cap.textContent).replace(/[()]/g, '') : '';
    if (cap) cap.remove();
    return { v: clean(c.textContent), pct };
  };
  let group = '';
  const rows = [];
  for (const n of document.querySelectorAll('[data-testid="wcl-headerSection-text"], [data-testid="wcl-statistics"]')) {
    if (n.getAttribute('data-testid') === 'wcl-headerSection-text') { group = clean(n.textContent); continue; }
    const label = n.querySelector('[class*="wcl-label_"]');
    const awayWrap = n.querySelector('[class*="wcl-awayValue_"]');
    const home = cell(n.querySelector('[class*="wcl-value_"]'));
    const away = cell(awayWrap ? awayWrap.querySelector('[class*="wcl-value_"]') : null);
    rows.push({ group, key: clean(label ? label.textContent : ''), home: home.v, away: away.v,
                homePct: home.pct, awayPct: away.pct });
  }
  const active = [...document.querySelectorAll('a[aria-current="page"][href*="/summary/stats/"]')]
    .map(a => a.getAttribute('href') || '');
  return { rows, active };
}"""


def clean_rows(rows: list[dict]) -> list[dict]:
    """Bỏ hàng không có nhãn; ô trống ⇒ "-" (cùng quy ước với player stats)."""
    out = []
    for r in rows:
        if not r.get("key"):
            continue
        out.append({"group": r.get("group", ""), "key": r["key"],
                    "home": r.get("home") or "-", "away": r.get("away") or "-",
                    "homePct": r.get("homePct") or "", "awayPct": r.get("awayPct") or ""})
    return out


def possession_reliable(scopes: dict) -> bool:
    """Flashscore hiện 50% – 50% khi giải không có số liệu kiểm soát bóng (đã thấy ở trận Johor).
    Mọi phạm vi có số đều đúng 50/50 ⇒ coi là không tin cậy."""
    seen = []
    for scope in scopes.values():
        if not scope:
            continue
        row = next((r for r in scope["rows"] if r["key"].lower() == "ball possession"), None)
        if row:
            seen.append((row["home"].replace(" ", ""), row["away"].replace(" ", "")))
    return bool(seen) and not all(pair == ("50%", "50%") for pair in seen)


def _read_scope(page, slug: str) -> list[dict] | None | bool:
    """→ hàng của phạm vi; None = hết giờ chờ (thử lại được); False = phạm vi không tồn tại (không thử lại)."""
    try:
        page.wait_for_selector('[data-testid="wcl-statistics"]', timeout=12_000)
    except PlaywrightTimeout:
        return None
    last = None
    for _ in range(12):                               # chờ số hàng ổn định qua 2 lần đọc
        raw = page.evaluate(JS_TEAM_STATS)
        if last is not None and len(raw["rows"]) == len(last["rows"]) and raw["rows"]:
            break
        last = raw
        page.wait_for_timeout(250)
    # Link tab con đang chọn (vd ".../summary/stats/1st-half/?mid=…"); link tab STATS cấp trên cũng có
    # aria-current nên chỉ xét các link có thêm một đoạn sau "/summary/stats/".
    subs = [h for h in raw["active"] if re.search(r"/summary/stats/[^/?#]+/", h)]
    if subs and not any(f"/summary/stats/{slug}/" in h for h in subs):
        return False                                  # Flashscore chuyển hướng (vd không có số liệu theo hiệp)
    rows = clean_rows(raw["rows"])
    return rows or None


def scrape_team_stats(pages, ref, deadline: float | None = None) -> dict | None:
    """pages: 1..n trang của cùng context (tải song song như player stats). → result.teamStats hoặc None.

    deadline (time.monotonic): quá hạn thì bỏ các phạm vi còn lại — team stats là dữ liệu MỀM, không được
    làm cả job vượt ngân sách (E_TIMEOUT)."""
    if not isinstance(pages, (list, tuple)):
        pages = [pages]
    scopes: dict[str, dict | None] = {key: None for _, key in SCOPES}
    batches = [SCOPES[i:i + len(pages)] for i in range(0, len(SCOPES), len(pages))]
    for batch in batches:
        if deadline is not None and time.monotonic() > deadline:
            break
        for page, (slug, _) in zip(pages, batch):
            goto(page, ref.url(f"summary/stats/{slug}"), wait_until="commit")
        for page, (slug, key) in zip(pages, batch):
            page.bring_to_front()                         # tab nền không được vẽ đầy đủ (xem player_stats)
            if deadline is not None and time.monotonic() > deadline:
                print(f"  ⚠ Bỏ qua team stats ({slug}): sắp hết ngân sách thời gian")
                continue
            rows = None
            for attempt in range(2):                  # Flashscore chậm ⇒ tải lại 1 lần (như player stats)
                try:
                    if attempt:
                        goto(page, ref.url(f"summary/stats/{slug}"))
                    rows = _read_scope(page, slug)
                except (CrawlError, PlaywrightError) as exc:
                    print(f"  ⚠ Không đọc được team stats ({slug}): {exc}")
                    rows = None
                if rows or rows is False:
                    break
                print(f"  ⚠ Team stats ({slug}) chưa hiện sau lần thử {attempt + 1}")
            rows = rows or None
            scopes[key] = {"rows": rows} if rows else None
    if not scopes["overall"]:
        return None
    return {**scopes, "possessionReliable": possession_reliable(scopes)}
