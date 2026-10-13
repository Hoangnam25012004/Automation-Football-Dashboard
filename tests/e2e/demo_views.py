"""Chụp "golden snapshot" của dashboard (design doc §9.3).

Với mỗi chế độ đội × tab: innerHTML của tab (bỏ nội dung các ô Match story `#lc-*` vì OCR
chạy bất đồng bộ), scorebar, tab nav, trạng thái nút, và dữ liệu mọi biểu đồ Chart.js.
"""
from __future__ import annotations

import difflib

TAB_IDS = ["overall", "shots", "attack", "passes", "defense", "goalkeeping"]
TEAMS = ["all", "home", "away"]

CAPTURE_JS = r"""
([team, tab]) => {
  App.setTeam(team); App.setTab(tab);
  const el = document.getElementById('tc-' + tab);
  const clone = el.cloneNode(true);
  clone.querySelectorAll('[id^="lc-"]').forEach(n => { n.innerHTML = ''; });
  const plain = v => v == null ? null : JSON.parse(JSON.stringify(v));
  const charts = Object.keys(state.charts).sort().map(k => {
    const c = state.charts[k];
    return { key: k, type: c.config.type, labels: plain(c.data.labels || []),
      datasets: (c.data.datasets || []).map(d => ({ label: d.label ?? null, data: plain(d.data),
        backgroundColor: plain(d.backgroundColor), borderColor: plain(d.borderColor) })) };
  });
  return {
    html: clone.innerHTML,
    scorebar: document.getElementById('scorebar').innerHTML,
    tabNav: document.getElementById('tabNav').innerHTML,
    toggleDisplay: document.getElementById('teamToggle').style.display,
    activeTabs: [...document.querySelectorAll('.tab-btn.active')].map(b => b.dataset.tab),
    activePills: [...document.querySelectorAll('.toggle-pill.active')].map(b => b.dataset.team),
    footMatch: document.getElementById('footMatch').textContent,
    buttons: { reset: document.getElementById('btnReset').style.display, exportPdf: document.getElementById('btnExport').style.display },
    charts,
  };
}
"""


def view_keys() -> list[tuple[str, str]]:
    return [(team, tab) for team in TEAMS for tab in TAB_IDS if not (tab == "overall" and team != "all")]


def open_dashboard_from_demo(page, url: str) -> None:
    page.goto(url, wait_until="load")
    page.wait_for_function("typeof App !== 'undefined' && typeof Chart !== 'undefined'")
    page.evaluate("App.loadDemo()")
    page.wait_for_selector("#dashboard.active", timeout=15000)


def capture_views(page) -> dict:
    return {f"{team}/{tab}": page.evaluate(CAPTURE_JS, [team, tab]) for team, tab in view_keys()}


def diff_views(golden: dict, views: dict, *, only: list[str] | None = None,
               html_prefix_until: dict[str, str] | None = None) -> list[str]:
    """So sánh; trả về danh sách mô tả khác biệt (rỗng = giống hệt).

    html_prefix_until: {view_key: marker} — chỉ so phần html TRƯỚC marker (dùng cho Overall
    khi khối Match story khác nguồn dữ liệu có chủ đích).
    """
    problems: list[str] = []
    keys = only or sorted(golden)
    for key in keys:
        if key not in views:
            problems.append(f"{key}: thiếu view")
            continue
        g, v = golden[key], views[key]
        for field in g:
            gv, vv = g[field], v.get(field)
            if field == "html" and html_prefix_until and key in html_prefix_until:
                marker = html_prefix_until[key]
                gv = gv.split(marker)[0]
                vv = (vv or "").split(marker)[0]
            if gv != vv:
                if isinstance(gv, str) and isinstance(vv, str):
                    d = list(difflib.unified_diff(gv.split("><"), vv.split("><"), lineterm="", n=1))[:30]
                    problems.append(f"{key}.{field} khác:\n    " + "\n    ".join(d))
                else:
                    problems.append(f"{key}.{field} khác: golden={str(gv)[:200]} | hiện tại={str(vv)[:200]}")
    return problems
