"""Lineups có cấu trúc từ DOM (quyết định D3; design doc §5.3, §6.6, Phụ lục D.2).

Kết quả có CÙNG hình dạng với LineupOCR.compute() của web, để gán thẳng vào state.lineupText;
renderer hiện có tự vẽ mà không chạy OCR. Tên lấy theo player-id từ roster của bảng stats để
ratingFor() (so khớp tên chính xác) luôn tìm được rating.
"""
from __future__ import annotations

from itertools import zip_longest

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .browser import NARROW, goto
from .errors import Warnings

JS_LINEUPS = r"""() => {
  const T = e => e ? (e.textContent || '').replace(/\s+/g, ' ').trim() : '';
  const pidOf = e => {
    const x = e && (e.matches('[data-analytics-player-id]') ? e : e.querySelector('[data-analytics-player-id]'));
    return x ? x.getAttribute('data-analytics-player-id') : null;
  };
  const out = { groups: [], formation: null };

  // 1) list groups: substituted players / starting lineups / substitutes / coaches
  document.querySelectorAll('[data-testid="wcl-lineupsGroup"]').forEach(g => {
    const head = T(g.querySelector('[data-testid="wcl-headerSection-text"]')).toLowerCase();
    const sides = [...g.querySelectorAll('[class*="wcl-side_"]')];
    out.groups.push({ head, sides: sides.map(sideEl => [...sideEl.children].map(item => {
      const sub = item.querySelector('[data-testid^="wcl-lineupsParticipantsSubstitution"]');
      if (sub) {                                              // ON player + OFF player + minute
        const offName = sub.querySelector('[class*="wcl-subName_"]');
        return {
          kind: 'sub',
          onId: pidOf(sub), onName: T(sub.querySelector('[class*="wcl-substitute_"] [class*="wcl-name_"]')),
          rating: T(sub.querySelector('[data-testid="wcl-badgeRating"]')) || null,
          offId: pidOf(offName && offName.closest('[data-analytics-player-id]')), offName: T(offName),
          minute: T(sub.querySelector('[class*="wcl-minute_"]')),
        };
      }
      const gen = item.querySelector('[data-testid^="wcl-lineupsParticipantGeneral"]');
      if (!gen) return null;
      return {
        kind: 'general',
        id: pidOf(gen), num: T(gen.querySelector('[class*="wcl-number_"]')) || null,
        name: T(gen.querySelector('[class*="wcl-name_"]')), role: T(gen.querySelector('[class*="wcl-roles_"]')) || null,
      };
    }).filter(Boolean)) });
  });

  // 2) formation: rows are ordered GK -> forwards; x/y normalised to the pitch box
  const field = document.querySelector('[data-testid="wcl-lineupsField"]');
  if (field) {
    const fb = field.getBoundingClientRect();
    const read = side => {
      const root = document.querySelector('[class*="fp-formation_"][class*="fp-' + side + '_"]');
      return root ? [...root.querySelectorAll('[class*="fp-row_"]')].map(row =>
        [...row.querySelectorAll('[class*="fp-player_"]')].map(pl => {
          const b = pl.getBoundingClientRect();
          return { id: pidOf(pl), num: T(pl.querySelector('[class*="wcl-participantNumber_"]')),
                   x: +(((b.left + b.width / 2) - fb.left) / fb.width).toFixed(3),
                   y: +(((b.top + b.height / 2) - fb.top) / fb.height).toFixed(3) };
        })) : [];
    };
    out.formation = {
      label: [...document.querySelectorAll('[class*="fp-headerFormation_"] > span')].map(T),
      home: read('home'), away: read('away'),
    };
  }
  return out;
}"""

# Placeholder 1×1 trong suốt: chỉ là "công tắc" cho renderOverall() dựng thẻ Match story (§5.4).
PLACEHOLDER_PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
                   "YAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
LINEUP_KEYS = ("formation", "starting_xi", "substituted", "substitutes", "coaches")
_HEADINGS = {"starting lineups": "starting", "substitutes": "bench",
             "substituted players": "changes", "coaches": "coaches"}


def _classify(groups: list[dict]) -> dict[str, list]:
    """Nhóm theo tiêu đề (en-GB); tiêu đề lạ ⇒ phân loại theo cấu trúc (design doc §6.6)."""
    out: dict[str, list] = {}
    unknown = []
    for g in groups:
        key = _HEADINGS.get(g["head"])
        if key and key not in out:
            out[key] = g["sides"]
        else:
            unknown.append(g)
    for g in unknown:
        sides = g["sides"]
        flat = [p for side in sides for p in side]
        if any(p["kind"] == "sub" for p in flat):
            key = "changes"
        elif "starting" not in out and sides and min(len(s) for s in sides) >= 9:
            key = "starting"
        elif all(len(s) <= 1 for s in sides) and not any(p.get("num") for p in flat):
            key = "coaches"
        else:
            key = "bench"
        out.setdefault(key, sides)
    return out


def _minute(text: str) -> str:
    return (text or "").strip().rstrip("'’").strip()


def build_lineups(raw: dict, roster: dict[str, str], warnings: Warnings) -> dict:
    """roster: player-id → tên như trong bảng stats. → dict 5 khoá (khoá thiếu dữ liệu = None)."""
    groups = _classify(raw.get("groups") or [])
    list_names: dict[str, str] = {}
    for sides in groups.values():
        for side in sides:
            for p in side:
                if p["kind"] == "general" and p.get("id") and p.get("name"):
                    list_names[p["id"]] = p["name"]

    def name_of(pid: str | None, fallback: str) -> str:
        if pid and pid in roster:
            return roster[pid]
        if pid and pid in list_names:
            return list_names[pid]
        return fallback or ""

    def cell(p: dict | None) -> dict:
        return {"name": name_of(p.get("id"), p.get("name", "")), "ok": True} if p else {"name": "", "ok": False}

    def two_col(sides: list | None) -> list | None:
        if not sides or len(sides) < 2 or not (sides[0] or sides[1]):
            return None
        rows = []
        for h, a in zip_longest(sides[0], sides[1]):
            rows.append({"homeNum": (h or {}).get("num") or "", "awayNum": (a or {}).get("num") or "",
                         "home": cell(h), "away": cell(a)})
        return rows

    result: dict = {key: None for key in LINEUP_KEYS}
    result["starting_xi"] = two_col(groups.get("starting"))
    result["substitutes"] = two_col(groups.get("bench"))

    changes = groups.get("changes")
    if changes and len(changes) >= 2:
        result["substituted"] = {
            side: [{"on": name_of(p.get("onId"), p.get("onName", "")), "off": name_of(p.get("offId"), p.get("offName", "")),
                    "min": _minute(p.get("minute", ""))} for p in changes[i] if p["kind"] == "sub"]
            for i, side in enumerate(("home", "away"))
        }

    coaches = groups.get("coaches")
    if coaches and len(coaches) >= 2 and (coaches[0] or coaches[1]):
        pick = lambda side: {"name": side[0]["name"], "ok": True} if side and side[0].get("name") else {"name": "—", "ok": False}
        result["coaches"] = {"home": pick(coaches[0]), "away": pick(coaches[1])}

    result["formation"] = layout_formation(raw.get("formation"), name_of)
    if raw.get("formation") is not None and result["formation"] is None:
        warnings.add("W_NO_FORMATION")

    starting = groups.get("starting")
    if result["starting_xi"] is None:
        warnings.add("W_LINEUPS_PARTIAL", "starting line-ups missing")
    elif starting and any(len(s) != 11 for s in starting[:2]):
        warnings.add("W_LINEUPS_PARTIAL", f"starting line-ups have {len(starting[0])}+{len(starting[1])} players")
    if starting and roster:
        missing = [p.get("name") for side in starting[:2] for p in side if p.get("id") not in roster]
        if missing:
            warnings.add("W_ROSTER_MISMATCH", ", ".join(missing[:5]))
    return result


def layout_formation(raw: dict | None, name_of) -> dict | None:
    """Toạ độ theo quy ước parseFormation: đội nhà GK 0.10 → tiền đạo 0.43; khách tiền đạo 0.57 → GK 0.90.

    x giữ số đo ở viewport hẹp (sân dọc); thứ tự trong hàng sắp theo x vì thứ tự DOM của đội
    khách là phải→trái.
    """
    if not raw:
        return None
    players = []
    for side in ("home", "away"):
        rows = [row for row in (raw.get(side) or []) if row]
        n = len(rows)
        for ri, row in enumerate(rows):
            if n == 1:
                t = 0.5
            else:
                t = ri / (n - 1) if side == "home" else (n - 1 - ri) / (n - 1)
            y = (0.10 if side == "home" else 0.57) + 0.33 * t
            for p in sorted(row, key=lambda q: q["x"]):
                players.append({"num": p.get("num") or "", "name": name_of(p.get("id"), "#" + (p.get("num") or "?")),
                                "ok": True, "side": side, "x": round(float(p["x"]), 4), "y": round(y, 4)})
    if len(players) < 4:
        return None
    return {"players": players, "w": 100, "h": 176}


def start_lineups(ctx, ref):
    """Mở trang lineups (viewport hẹp) và phát lệnh tải ngay — để nó tải song song với player stats."""
    page = ctx.new_page()
    page.set_viewport_size(NARROW)
    goto(page, ref.url("summary/lineups"), wait_until="commit")
    return page


def scrape_lineups(ctx, ref, roster: dict[str, str], warnings: Warnings, page=None) -> dict | None:
    """page: trang đã mở bằng start_lineups (nếu có); không có thì tự mở và tải."""
    if page is None:
        page = ctx.new_page()
        page.set_viewport_size(NARROW)
        goto(page, ref.url("summary/lineups"))
    try:
        try:
            page.wait_for_selector('[data-testid="wcl-lineupsGroup"]', timeout=10_000)
        except PlaywrightTimeout:
            warnings.add("W_NO_LINEUPS")
            return None
        try:
            page.wait_for_selector('[data-testid="wcl-lineupsField"] [class*="fp-player_"]', timeout=3_000)
        except PlaywrightTimeout:
            pass                                  # có trận có lineups nhưng không có sơ đồ
        raw = page.evaluate(JS_LINEUPS)
    finally:
        page.close()
    lineups = build_lineups(raw, roster, warnings)
    if not any(lineups.values()):
        warnings.add("W_NO_LINEUPS")
        return None
    return lineups


def lineup_images(lineups: dict | None) -> dict:
    """Bất biến §5.4: lineupImages[key] tồn tại ⇔ lineups[key] khác None."""
    if not lineups:
        return {}
    return {key: PLACEHOLDER_PNG for key in LINEUP_KEYS if lineups.get(key)}
