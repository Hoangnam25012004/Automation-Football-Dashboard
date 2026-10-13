"""Lưu fragment HTML từ trang thật làm fixture cho test offline (design doc §9.5).

  python tools/capture_fixtures.py <link trận>
  → tests/fixtures/<mid>/header.html, timeline.html, lineups.html, stats_top_<MÃ>.html, result.json
  python tools/capture_fixtures.py --timeline-only <link trận> [<link trận> …]
  → tests/fixtures/<mid>/header.html, timeline.html   (cho test các loại sự kiện hiếm)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from crawler import browser as fsb  # noqa: E402
from crawler import crawl  # noqa: E402
from crawler.player_stats import _detect_teams, _select_team, _wait_for_team_table, JS_TABLE  # noqa: E402
from crawler.urls import parse_match_url  # noqa: E402

OUTER = "s => { const e = document.querySelector(s); return e ? e.outerHTML : null; }"


def capture_timelines(urls: list[str]) -> int:
    with sync_playwright() as p:
        browser = fsb.launch(p)
        try:
            ctx = fsb.new_context(browser)
            page = ctx.new_page()
            for index, url in enumerate(urls):
                ref = parse_match_url(url)
                folder = ROOT / "tests" / "fixtures" / (ref.mid or "nomid")
                folder.mkdir(parents=True, exist_ok=True)
                fsb.goto(page, ref.url())
                if index == 0:
                    fsb.dismiss_consent(page, ctx)
                page.wait_for_selector(".duelParticipant .participant__participantName")
                page.wait_for_selector(".smv__verticalSections")
                (folder / "header.html").write_text(page.evaluate(OUTER, ".duelParticipant"), encoding="utf-8")
                (folder / "timeline.html").write_text(page.evaluate(OUTER, ".smv__verticalSections"), encoding="utf-8")
                print(f"✓ {folder.relative_to(ROOT)}  ({page.title()})")
        finally:
            browser.close()
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) >= 3 and sys.argv[1] == "--timeline-only":
        return capture_timelines(sys.argv[2:])
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    url = sys.argv[1]
    ref = parse_match_url(url)
    folder = ROOT / "tests" / "fixtures" / (ref.mid or "nomid")
    folder.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = fsb.launch(p)
        try:
            ctx = fsb.new_context(browser)
            page = ctx.new_page()
            fsb.goto(page, ref.url())
            fsb.dismiss_consent(page, ctx)
            page.wait_for_selector(".duelParticipant .participant__participantName")
            page.wait_for_selector(".smv__verticalSections")
            (folder / "header.html").write_text(page.evaluate(OUTER, ".duelParticipant"), encoding="utf-8")
            (folder / "timeline.html").write_text(page.evaluate(OUTER, ".smv__verticalSections"), encoding="utf-8")

            fsb.goto(page, ref.url("summary/player-stats/top"))
            page.wait_for_selector('[data-testid="wcl-table"]')
            previous = {r["id"] or r["name"] for r in page.evaluate(JS_TABLE)["rows"]}
            for index, code in enumerate(_detect_teams(page)):
                _select_team(page, code, index)
                table = _wait_for_team_table(page, previous)
                previous = {r["id"] or r["name"] for r in table["rows"]}
                fragment = ("<div>" + page.evaluate(OUTER, '[data-testid="wcl-selectButton"]')
                            + page.evaluate(OUTER, '[data-testid="wcl-table"]') + "</div>")
                (folder / f"stats_top_{code}.html").write_text(fragment, encoding="utf-8")

            page.set_viewport_size(fsb.NARROW)
            fsb.goto(page, ref.url("summary/lineups"))
            page.wait_for_selector('[data-testid="wcl-lineupsGroup"]')
            (folder / "lineups.html").write_text(page.evaluate(OUTER, '[data-analytics-context="widget-lineups"]'),
                                                 encoding="utf-8")
        finally:
            browser.close()

    result = crawl(url)
    (folder / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    for f in sorted(folder.iterdir()):
        print(f"✓ {f.relative_to(ROOT)}  ({f.stat().st_size:,} byte)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
