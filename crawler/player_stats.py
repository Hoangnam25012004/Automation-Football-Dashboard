"""Player stats: 7 tab × 2 đội (design doc §6.4).

Giữ đúng ngữ nghĩa đọc bảng của flashscore_scraper.py (legacy) để dữ liệu giống hệt luồng
xlsx cũ: header = ["Player", "Position", *th[1:]], ô trống = "-", chuỗi lấy bằng innerText.
Khác legacy: mỗi tab chỉ `goto` một lần rồi đổi đội ngay trong trang (14 → 7 lần tải),
và có kiểm tra bảng đã đổi xong trước khi đọc.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .browser import goto
from .errors import CrawlError, Warnings
from .header import MatchInfo, logo_name

TABS = [("top", "Top Stats"), ("shots", "Shots"), ("attack", "Attack"), ("passes", "Passes"),
        ("defense", "Defense"), ("goalkeeping", "Goalkeeping"), ("general", "General")]

JS_TABLE = r"""() => {
  const table = document.querySelector('[data-testid="wcl-table"]');
  if (!table) return null;
  const head = table.querySelector('[data-testid="wcl-tableHead"]');
  const heads = head ? [...head.querySelectorAll('th')].map(th => (th.innerText || '').trim()) : [];
  const body = table.querySelector('[data-testid="wcl-tableBody"]') || table;
  const rows = [...body.querySelectorAll('[data-testid="wcl-tableBodyRow"]')].map(tr => {
    const cells = [...tr.querySelectorAll('[data-testid="wcl-tableBodyCell"]')];
    const pc = tr.querySelector('[data-testid="wcl-playerCell"]');
    const first = pc || cells[0];
    const lines = first ? (first.innerText || '').trim().split('\n').map(s => s.trim()).filter(Boolean) : [];
    const logo = pc ? pc.querySelector('[class*="wcl-teamLogo_"] img') : null;
    return {
      id: pc ? pc.getAttribute('data-analytics-player-id') : null,
      name: lines[0] || '', position: lines[1] || '',
      stats: cells.slice(1).map(td => (td.innerText || '').trim()),
      logo: logo ? (logo.getAttribute('src') || '') : '',
    };
  });
  const button = document.querySelector('[data-testid="wcl-selectButton"]');
  return { heads, rows, selected: button ? (button.innerText || '').trim() : '' };
}"""

JS_OPTIONS = "() => [...document.querySelectorAll('[role=\"option\"]')].map(o => (o.innerText || '').trim())"


@dataclass
class StatsResult:
    home: str                                   # mã đội nhà (vd "JOH")
    away: str
    teams: dict[str, dict[str, dict]]           # {mã: {"Top Stats": {"headers": [...], "rows": [...]}, ...}}
    roster: dict[str, tuple[str, str]] = field(default_factory=dict)   # player-id → (mã đội, tên)


def _headers(heads: list[str]) -> list[str]:
    out: list[str] = []
    for i, text in enumerate(heads):
        if i == 0:
            out += ["Player", "Position"]        # th đầu = nút lọc đội ("ALL"/mã đội)
        else:
            out.append(text if text else f"Col{i}")
    return out or ["Player", "Position"]


def _records(headers: list[str], rows: list[dict]) -> list[dict]:
    records = []
    for row in rows:
        cells = [row["name"], row["position"]] + [s if s else "-" for s in row["stats"]]
        if not any(c for c in cells if c not in ("", "-")):
            continue                              # legacy bỏ dòng rỗng
        record = {h: (cells[i] if i < len(cells) and cells[i] != "" else "-") for i, h in enumerate(headers)}
        if record.get("Player", "-") != "-":      # parseStatsSheet chỉ giữ dòng có tên cầu thủ
            records.append(record)
    return records


def _detect_teams(page) -> list[str]:
    """Đọc combobox đội; nhãn = token cuối (vd "England ENG" → "ENG"), bỏ "ALL" — như legacy."""
    page.locator('[data-testid="wcl-selectButton"]').first.click(timeout=5_000)
    page.locator('[role="option"]').first.wait_for(state="visible", timeout=5_000)
    texts = page.evaluate(JS_OPTIONS)
    page.keyboard.press("Escape")
    labels = []
    for text in texts:
        parts = text.split()
        label = parts[-1] if parts else text
        if label and label.upper() != "ALL":
            labels.append(label)
    return labels[:2]


def _select_team(page, label: str, index: int) -> None:
    page.locator('[data-testid="wcl-selectButton"]').first.click(timeout=5_000)
    options = page.locator('[role="option"]')
    options.first.wait_for(state="visible", timeout=5_000)
    texts = page.evaluate(JS_OPTIONS)
    team_positions = [k for k, t in enumerate(texts) if (t.split() or [""])[-1].upper() != "ALL"]
    target = None
    for k in team_positions:
        if (texts[k].split() or [""])[-1].upper() == label.upper() and texts.count(texts[k]) == 1:
            target = k
            break
    if target is None:                            # trùng nhãn ⇒ chọn theo thứ tự option
        target = team_positions[index]
    options.nth(target).click(timeout=5_000)


def _wait_for_team_table(page, previous_ids: set, timeout_s: float = 6.0) -> dict | None:
    """Chờ tới khi bảng hiển thị tập cầu thủ khác bảng trước đó và ổn định qua 2 lần đọc.

    Hết giờ ⇒ None (KHÔNG trả bảng cũ — tránh gán nhầm dữ liệu của đội khác).
    """
    deadline = time.monotonic() + timeout_s
    last_ids = None
    while time.monotonic() < deadline:
        table = page.evaluate(JS_TABLE)
        ids = tuple(r["id"] or r["name"] for r in (table or {}).get("rows", []))
        if ids and set(ids) != previous_ids:
            if ids == last_ids:
                return table
            last_ids = ids
        page.wait_for_timeout(150)
    return None


def scrape_player_stats(pages, ref, info: MatchInfo, warnings: Warnings, progress=None) -> StatsResult:
    """pages: 1..n trang của cùng context. Các tab được xử lý theo lô n tab: phát lệnh điều hướng cho
    cả lô trước (trình duyệt tải song song), rồi lần lượt đọc từng trang — Playwright sync vẫn chỉ
    chạy trong một thread."""
    if not isinstance(pages, (list, tuple)):
        pages = [pages]
    teams: list[str] = []
    data: dict[str, dict[str, dict]] = {}
    roster: dict[str, tuple[str, str]] = {}
    team_ids: dict[str, set] = {}
    order_checked = False

    batches = [list(enumerate(TABS))[i:i + len(pages)] for i in range(0, len(TABS), len(pages))]
    for batch in batches:
        for page, (_, (slug, _label)) in zip(pages, batch):        # phát lệnh tải cả lô
            goto(page, ref.url(f"summary/player-stats/{slug}"), wait_until="commit")
        for page, (tab_index, (slug, label)) in zip(pages, batch):  # rồi đọc từng trang
            if progress:
                progress(f"Reading player stats · {label} ({tab_index + 1}/{len(TABS)})…")
            table = None
            for attempt in range(2):
                if attempt:
                    goto(page, ref.url(f"summary/player-stats/{slug}"))
                try:
                    page.wait_for_selector('[data-testid="wcl-table"]', timeout=15_000)
                    table = page.evaluate(JS_TABLE)
                    break
                except PlaywrightTimeout:
                    table = None
            if table is None:
                if tab_index == 0 and not page.locator('a[href*="player-stats"], [role="tab"]:has-text("Player stats")').count():
                    raise CrawlError("E_NO_PLAYER_STATS")
                warnings.add("W_STATS_TAB_EMPTY", label)
                for code in teams:
                    data[code][label] = {"headers": [], "rows": []}
                continue

            if not teams:
                labels = _detect_teams(page)
                if len(labels) < 2:
                    raise CrawlError("E_NO_PLAYER_STATS", hint="Flashscore does not split these player stats by team.")
                if labels[0].upper() == labels[1].upper():
                    warnings.add("W_TEAM_CODE_COLLISION", labels[0])
                    labels = ["HOME", "AWAY"]
                teams = labels
                data = {code: {} for code in teams}
                team_ids = {code: set() for code in teams}

            previous = {r["id"] or r["name"] for r in table["rows"]}
            for team_index, code in enumerate(list(teams)):
                _select_team(page, code, team_index)
                current = _wait_for_team_table(page, previous)
                if current is None:
                    warnings.add("W_STATS_TAB_EMPTY", f"{label} ({code})")
                    data[code][label] = {"headers": [], "rows": []}
                    continue
                ids = {r["id"] for r in current["rows"] if r["id"]}
                others = [c for c in team_ids if c != code]
                if others and ids & team_ids[others[0]]:
                    raise CrawlError("E_INTERNAL", "Player stats of the two teams overlap; the team filter did not apply.")
                team_ids[code] |= ids
                headers = _headers(current["heads"])
                data[code][label] = {"headers": headers, "rows": _records(headers, current["rows"])}
                for row in current["rows"]:
                    if row["id"] and row["name"]:
                        roster[row["id"]] = (code, row["name"])
                previous = {r["id"] or r["name"] for r in current["rows"]}

                if not order_checked and team_index == 0 and current["rows"]:
                    order_checked = True
                    first_logo = logo_name(current["rows"][0]["logo"])
                    if first_logo and first_logo == logo_name(info.away_logo_url) != logo_name(info.home_logo_url):
                        warnings.add("W_TEAM_ORDER_SWAPPED")
                        teams.reverse()

    if not teams:
        raise CrawlError("E_NO_PLAYER_STATS")
    if not any(data[c].get("Top Stats", {}).get("rows") or data[c].get("General", {}).get("rows") for c in teams):
        raise CrawlError("E_NO_PLAYER_STATS")
    ordered = {code: {label: data[code].get(label, {"headers": [], "rows": []}) for _, label in TABS} for code in teams}
    return StatsResult(home=teams[0], away=teams[1], teams=ordered, roster=roster)
