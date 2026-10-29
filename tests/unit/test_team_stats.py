"""Team stats cấp đội + metadata trận (design doc dashboard-redesign §3.2–§3.4), chạy offline trên fixture."""
import json
import unittest

from playwright.sync_api import sync_playwright

from crawler.header import JS_META, parse_meta
from crawler.team_stats import JS_TEAM_STATS, SCOPES, clean_rows, possession_reliable
from tests import _support

MIDS = ("vLuGlk0n", "GGiPsLP1", "d8pxv90m")


def result(mid: str) -> dict:
    return json.loads((_support.FIXTURES / mid / "result.json").read_text(encoding="utf-8"))


class OfflineTeamStatsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)
        cls.page = cls.browser.new_page()
        cls.page.route("**/*", lambda route: route.abort())          # offline tuyệt đối

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def load(self, mid: str, name: str):
        self.page.set_content("<!doctype html><html><body>"
                              + (_support.FIXTURES / mid / name).read_text(encoding="utf-8") + "</body></html>")
        return self.page

    def test_rows_match_result_for_every_scope(self):
        for mid in MIDS:
            expected = result(mid)["teamStats"]
            for slug, key in SCOPES:
                with self.subTest(match=mid, scope=slug):
                    raw = self.load(mid, f"team_stats_{slug}.html").evaluate(JS_TEAM_STATS)
                    self.assertEqual(clean_rows(raw["rows"]), expected[key]["rows"])
                    self.assertEqual(len(raw["rows"]), 45)
                    self.assertTrue(any(f"/summary/stats/{slug}/" in h for h in raw["active"]))

    def test_known_values(self):
        rows = {r["key"]: r for r in result("GGiPsLP1")["teamStats"]["overall"]["rows"] if r["group"] != "Top stats"}
        self.assertEqual((rows["Expected goals (xG)"]["home"], rows["Expected goals (xG)"]["away"]), ("0.57", "3.20"))
        self.assertEqual(rows["Accurate passes"], {"group": "Passes", "key": "Accurate passes", "home": "283",
                                                   "away": "539", "homePct": "81%", "awayPct": "90%"})
        self.assertEqual((rows["Corner kicks"]["home"], rows["Corner kicks"]["away"]), ("4", "8"))
        self.assertIn("Goals prevented", rows)
        johor = {r["key"]: r for r in result("vLuGlk0n")["teamStats"]["firstHalf"]["rows"]}
        self.assertEqual((johor["Expected goals (xG)"]["home"], johor["Expected goals (xG)"]["away"]), ("1.65", "0.06"))

    def test_possession_reliability(self):
        self.assertFalse(result("vLuGlk0n")["teamStats"]["possessionReliable"])    # 50/50 ở cả 3 phạm vi
        self.assertTrue(result("GGiPsLP1")["teamStats"]["possessionReliable"])     # 37/63
        fake = {"overall": {"rows": [{"key": "Ball possession", "home": "50%", "away": "50%"}]},
                "firstHalf": {"rows": [{"key": "Ball possession", "home": "48%", "away": "52%"}]}, "secondHalf": None}
        self.assertTrue(possession_reliable(fake))
        self.assertFalse(possession_reliable({"overall": {"rows": []}, "firstHalf": None, "secondHalf": None}))

    def test_meta(self):
        expected = {"vLuGlk0n": ("ASEAN Club Championship", "Asia", "Kim Woo-Sung (Kor)", "Sultan Ibrahim Stadium (Johor Bahru)"),
                    "GGiPsLP1": ("LaLiga - Round 6", "Spain", "Ortiz M. (Esp)", "Estadio La Rosaleda (Málaga)"),
                    "d8pxv90m": ("DFB Pokal - 1/32-finals", "Germany", "Wienefeld J. (Ger)", "Stadion auf dem Wurfplatz (Berlin)")}
        for mid, (comp, country, referee, venue) in expected.items():
            with self.subTest(match=mid):
                meta = parse_meta(self.load(mid, "meta.html").evaluate(JS_META), "01.01.2026 20:00")
                self.assertEqual(meta, {"competition": comp, "country": country, "kickoff": "01.01.2026 20:00",
                                        "referee": referee, "venue": venue})
                self.assertEqual({k: v for k, v in result(mid)["meta"].items() if k != "kickoff"},
                                 {k: v for k, v in meta.items() if k != "kickoff"})

    def test_deadline_passed_skips_without_loading(self):
        class NoPage:                                   # mọi lệnh điều hướng đều là lỗi
            def goto(self, *a, **k):
                raise AssertionError("không được tải trang khi đã quá hạn")
        from crawler.team_stats import scrape_team_stats
        from crawler.urls import parse_match_url
        ref = parse_match_url("https://www.flashscore.com/match/football/a-AAAAAAAA/b-BBBBBBBB/?mid=CCCCCCCC")
        self.assertIsNone(scrape_team_stats([NoPage()], ref, deadline=0.0))

    def test_meta_missing_is_empty_not_error(self):
        self.assertEqual(parse_meta({}, ""), {"competition": "", "country": "", "kickoff": "", "referee": "", "venue": ""})


if __name__ == "__main__":
    unittest.main()
