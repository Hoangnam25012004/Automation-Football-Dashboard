"""Canary trên bộ trận tham chiếu (design doc §9.6) — phát hiện sớm khi Flashscore đổi DOM.

FS_LIVE=1 python -m unittest tests.live.test_live_reference      (~6 phút, chạm flashscore.com)
Kỳ vọng quan sát ngày 2026-10-09; Flashscore có thể hiệu chỉnh số liệu nên chỉ kiểm những điều ổn định.
"""
import unittest

from crawler import CrawlError, crawl
from crawler.lineups import lineup_images
from crawler.player_stats import TABS
from crawler.timeline import GOAL_TYPES
from tests import _support

BASE = "https://www.flashscore.com/match/football/"
PANEL = [
    # (tên, link, mã nhà, mã khách, tổng bàn, loại sự kiện phải có, period phải có)
    ("Johor DT 6-0 Svay Rieng", BASE + "johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/?mid=vLuGlk0n", "JOH", "SVA", 6,
     {"Goal", "Yellow card", "Substitution"}, set()),
    ("Malaga 1-3 Villarreal: VAR + penalty", BASE + "malaga-25tIqYiJ/villarreal-lUatW5jE/?mid=GGiPsLP1", "MAL", "VIL", 4,
     {"VAR", "Penalty goal"}, set()),
    ("Peterborough 3-3 Barnsley: luân lưu sau 90'", BASE + "barnsley-UNGEKMx6/peterborough-tWeI85kh/?mid=rJi7Md3T",
     "PET", "BAR", 6, {"Goal"}, set()),
    ("Altglienicke 3-3 Wolfsburg: hiệp phụ + luân lưu", BASE + "altglienicke-EP8ggpyE/wolfsburg-nwkTahLL/?mid=d8pxv90m",
     "ALT", "WOL", 6, {"Goal"}, {"Extra time"}),
    ("Fulham 1-1 Man Utd: phản lưới", BASE + "fulham-69ZiU2Om/manchester-united-ppjDR086/?mid=vq6T9aFr", "FUL", "MNU", 2,
     {"Own goal"}, set()),
]


@unittest.skipUnless(_support.LIVE, "đặt FS_LIVE=1 để chạy test chạm flashscore.com")
class LiveReferencePanelTest(unittest.TestCase):
    def check(self, name, url, home, away, goals, types, halves):
        result = crawl(url)
        stats = result["stats"]
        self.assertEqual((stats["home"], stats["away"]), (home, away), name)
        for code in (home, away):
            self.assertEqual(list(stats["teams"][code]), [label for _, label in TABS], name)
            self.assertGreaterEqual(len(stats["teams"][code]["Top Stats"]["rows"]), 11, name)
            self.assertEqual(stats["teams"][code]["Top Stats"]["headers"][:3], ["Player", "Position", "Rating"], name)
        events = result["summary"]["events"]
        self.assertEqual(sum(e["type"] in GOAL_TYPES for e in events), goals, name)
        self.assertTrue(types <= {e["type"] for e in events}, f"{name}: {sorted({e['type'] for e in events})}")
        self.assertTrue(halves <= {e["half"] for e in events}, name)
        self.assertFalse(any(e["type"] == "Card" or e["half"] == "Penalties" for e in events), name)
        self.assertTrue(result["summary"]["homeLogo"] and result["summary"]["awayLogo"], name)
        lineups = result["lineups"]
        self.assertEqual(len(lineups["starting_xi"]), 11, name)
        self.assertEqual(len(lineups["formation"]["players"]), 22, name)
        self.assertEqual(result["lineupImages"], lineup_images(lineups), name)
        self.assertEqual(result["schemaVersion"], 2, name)
        for scope in ("overall", "firstHalf", "secondHalf"):          # tab STATS cấp đội (redesign §3.2)
            self.assertGreaterEqual(len(result["teamStats"][scope]["rows"]), 40, f"{name} {scope}")
        self.assertTrue(result["meta"]["competition"] and result["meta"]["kickoff"], name)
        self.assertEqual(result["warnings"], [], name)

    def test_panel(self):
        for case in PANEL:
            with self.subTest(match=case[0]):
                self.check(*case)

    def test_no_player_stats_fails_fast(self):
        with self.assertRaises(CrawlError) as ctx:
            crawl(BASE + "khanh-hoa-Myp07Vu0/xuan-thien-phu-tho-b7ogJJMf/?mid=r5x1FLmS")    # V.League 2
        self.assertEqual(ctx.exception.code, "E_NO_PLAYER_STATS")

    def test_link_without_mid_warns(self):
        result = crawl(BASE + "johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/")
        self.assertEqual([w["code"] for w in result["warnings"]], ["W_NO_MID"])
        self.assertEqual(result["stats"]["home"], "JOH")

    def test_scheduled_match_is_rejected(self):
        from playwright.sync_api import sync_playwright

        from crawler import browser as fsb
        with sync_playwright() as p:
            browser = fsb.launch(p)
            try:
                ctx = fsb.new_context(browser)
                page = ctx.new_page()
                fsb.goto(page, "https://www.flashscore.com/football/england/premier-league/fixtures/")
                fsb.dismiss_consent(page, ctx)
                page.wait_for_selector('[id^="g_1_"]', timeout=20000)
                page.wait_for_timeout(1500)
                links = page.evaluate("() => [...document.querySelectorAll('a[href*=\"/match/football/\"]')]"
                                      ".map(a => a.href).filter(h => h.includes('mid='))")
            finally:
                browser.close()
        self.assertTrue(links, "không tìm thấy trận sắp đá nào")
        with self.assertRaises(CrawlError) as ctx:
            crawl(links[-1])
        self.assertEqual(ctx.exception.code, "E_MATCH_NOT_FINISHED")


if __name__ == "__main__":
    unittest.main()
