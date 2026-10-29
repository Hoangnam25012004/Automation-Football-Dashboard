"""Điều phối một lần crawl (design doc §6.7): header + timeline → stats 7 tab → lineups → ghép.

Header và player stats là BẮT BUỘC (lỗi ⇒ dừng); timeline và lineups là MỀM (lỗi ⇒ cảnh báo).
"""
from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from . import browser as fsb
from .assemble import assemble
from .errors import CrawlError, Warnings
from .header import fetch_data_url, read_header, read_meta
from .lineups import scrape_lineups, start_lineups
from .player_stats import TABS, scrape_player_stats
from .team_stats import scrape_team_stats
from .timeline import read_timeline
from .urls import parse_match_url

TOTAL_STEPS = 2 + len(TABS) + 2          # header+timeline, 7 tab stats, team stats, lineups, ghép = 11
BUDGET_S = 150
TEAM_STATS_RESERVE_S = 25
ROOT = Path(__file__).resolve().parent.parent
_TABS_JS = "() => [...document.querySelectorAll('[role=\"tab\"]')].map(t => (t.textContent || '').trim().toLowerCase())"


class _Progress:
    def __init__(self, callback):
        self.callback = callback
        self.done = 0
        self.started = False

    def start(self, phase: str, message: str) -> None:
        if self.started:
            self.done += 1
        self.started = True
        if self.callback:
            self.callback({"phase": phase, "done": self.done, "total": TOTAL_STEPS, "message": message})

    def finish(self) -> None:
        self.done = TOTAL_STEPS
        if self.callback:
            self.callback({"phase": "done", "done": TOTAL_STEPS, "total": TOTAL_STEPS, "message": "Done"})


def _save_debug(page, ref, label: str) -> None:
    if os.environ.get("FS_DEBUG") != "1" or page is None:
        return
    try:
        folder = ROOT / "debug" / f"{datetime.now():%Y%m%d-%H%M%S}-{ref.mid or 'nomid'}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{label}.html").write_text(page.content(), encoding="utf-8")
        print(f"  ⚠ Đã lưu HTML gỡ lỗi: {folder / (label + '.html')}")
    except Exception as exc:                       # gỡ lỗi không được làm hỏng job
        print(f"  ⚠ Không lưu được HTML gỡ lỗi: {exc}")


def crawl(url: str, progress=None) -> dict:
    """Crawl một trận và trả về `result` theo hợp đồng §5.1. Ném CrawlError khi phải dừng."""
    ref = parse_match_url(url)
    warnings = Warnings()
    if not ref.mid:
        warnings.add("W_NO_MID")
    prog = _Progress(progress)
    t0 = time.monotonic()

    def within_budget() -> None:
        if time.monotonic() - t0 > BUDGET_S:
            raise CrawlError("E_TIMEOUT")

    with sync_playwright() as playwright:
        browser = fsb.launch(playwright)
        page = None
        stage = "header"
        try:
            ctx = fsb.new_context(browser)
            page = ctx.new_page()

            prog.start("header", "Opening match page…")
            response = fsb.goto(page, ref.url())
            if response is not None and response.status == 404:
                raise CrawlError("E_MATCH_NOT_FOUND")
            fsb.dismiss_consent(page, ctx)
            info = read_header(page)
            try:
                events, timeline_rows = read_timeline(page, info)
            except PlaywrightError as exc:
                print(f"  ⚠ Không đọc được timeline: {exc}")
                events, timeline_rows = [], 0
            logos = (fetch_data_url(ctx, info.home_logo_url), fetch_data_url(ctx, info.away_logo_url))
            meta = read_meta(page, info.start)

            # Thanh tab của trận cho biết trước có Player stats / Lineups không (giải nhỏ thường không có)
            # ⇒ báo lỗi ngay thay vì chờ bảng tới hết giờ. Không đọc được thanh tab ⇒ cứ thử như bình thường.
            tabs = page.evaluate(_TABS_JS)
            if tabs and "player stats" not in tabs:
                raise CrawlError("E_NO_PLAYER_STATS")
            has_lineups = not tabs or "lineups" in tabs
            has_team_stats = not tabs or "stats" in tabs

            # Tải song song (FS_PARALLEL, mặc định 3 trang): trang lineups bắt đầu tải ngay, các tab
            # player stats tải theo lô. Mọi thao tác Playwright vẫn ở cùng một thread.
            lineups_page = None
            if has_lineups and fsb.parallel() > 1:
                try:
                    lineups_page = start_lineups(ctx, ref)
                except (CrawlError, PlaywrightError) as exc:
                    print(f"  ⚠ Không mở trước được trang lineups: {exc}")
            stat_pages = [page] + [ctx.new_page() for _ in range(fsb.parallel() - 1)]

            stage = "player_stats"
            within_budget()
            stats = scrape_player_stats(
                stat_pages, ref, info, warnings,
                progress=lambda message: (within_budget(), prog.start("player_stats", message)))

            # Team stats (MỀM): dùng lại các trang của player stats.
            stage = "team_stats"
            within_budget()
            prog.start("team_stats", "Reading team stats…")
            team_stats = None
            if has_team_stats:
                try:   # chừa ≥ TEAM_STATS_RESERVE_S cho line-ups + ghép: dữ liệu mềm không được gây E_TIMEOUT
                    team_stats = scrape_team_stats(stat_pages, ref, deadline=t0 + BUDGET_S - TEAM_STATS_RESERVE_S)
                except (CrawlError, PlaywrightError) as exc:
                    print(f"  ⚠ Không đọc được team stats: {exc}")
            if team_stats is None:
                warnings.add("W_NO_TEAM_STATS")
            for extra in stat_pages[1:]:
                extra.close()

            stage = "lineups"
            within_budget()
            prog.start("lineups", "Reading line-ups…")
            roster = {pid: name for pid, (_, name) in stats.roster.items()}
            lineups = None
            if not has_lineups:
                warnings.add("W_NO_LINEUPS")
            else:
                for attempt in range(2):                # máy chậm (vd Hugging Face) đôi khi lỡ lần đầu ⇒ thử lại 1 lần, trang mới
                    try:
                        lineups = scrape_lineups(ctx, ref, roster, warnings, page=lineups_page if attempt == 0 else None)
                        break
                    except (CrawlError, PlaywrightError) as exc:
                        print(f"  ⚠ Không đọc được lineups (lần {attempt + 1}): {exc}")
                        if attempt == 1 or time.monotonic() - t0 > BUDGET_S - TEAM_STATS_RESERVE_S:
                            warnings.add("W_NO_LINEUPS")
                            break

            stage = "assemble"
            prog.start("assemble", "Building the report…")
            result = assemble(ref, info, stats, events, timeline_rows, logos, lineups, warnings,
                              team_stats=team_stats, meta=meta)
            prog.finish()
            return result
        except CrawlError:
            _save_debug(page, ref, stage)
            raise
        except PlaywrightError as exc:
            _save_debug(page, ref, stage)
            raise CrawlError("E_INTERNAL", hint=f"{type(exc).__name__} at step “{stage}”: {str(exc).splitlines()[0][:200]}") from exc
        finally:
            browser.close()
