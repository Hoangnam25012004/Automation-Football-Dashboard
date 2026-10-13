"""Chạy extractor JS trên fixture đã lưu (page.set_content, chặn toàn bộ mạng) — design doc §9.5.

Kỳ vọng lấy từ result.json chụp cùng lúc với fixture. Riêng hình học sơ đồ cần CSS thật của
Flashscore nên ở đây chỉ kiểm cấu trúc hàng; số đo thật do test live kiểm.
"""
import json
import unittest

from playwright.sync_api import sync_playwright

from crawler.errors import Warnings
from crawler.header import FINISHED, JS_HEADER
from crawler.lineups import JS_LINEUPS, build_lineups
from crawler.player_stats import JS_TABLE, _headers, _records
from crawler.timeline import JS_TIMELINE
from tests import _support

MID = "vLuGlk0n"
FIX = _support.FIXTURES / MID


class OfflineExtractorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected = json.loads((FIX / "result.json").read_text(encoding="utf-8"))
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)
        cls.page = cls.browser.new_page()
        cls.page.route("**/*", lambda route: route.abort())          # offline tuyệt đối

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def load(self, name: str, css: str = ""):
        style = f"<style>{css}</style>" if css else ""
        self.page.set_content("<!doctype html><html><head>" + style + "</head><body>"
                              + (FIX / name).read_text(encoding="utf-8") + "</body></html>")
        return self.page

    def test_header(self):
        raw = self.load("header.html").evaluate(JS_HEADER)
        self.assertEqual((raw["home"], raw["away"]), ("Johor DT", "Svay Rieng"))
        self.assertRegex(raw["score"], r"6\D+0")
        self.assertRegex(raw["status"].strip(), FINISHED)
        self.assertTrue(raw["homeLogo"].endswith(".png") and raw["awayLogo"].endswith(".png"))

    def test_timeline_matches_result(self):
        raw = self.load("timeline.html").evaluate(JS_TIMELINE)
        self.assertEqual(raw["rows"], 21)
        expected = [{k: v for k, v in e.items() if k != "team"} for e in self.expected["summary"]["events"]]
        self.assertEqual(raw["events"], expected)

    def test_stats_table_matches_result(self):
        # Mỗi <th> có thêm nút "bóng" (wcl-shadow_, aria-hidden) dùng để đo độ rộng; CSS của
        # Flashscore ẩn nó nên innerText trên trang thật chỉ có 1 lần tên cột. Fixture không có
        # CSS ⇒ tái tạo đúng quy tắc ẩn đó.
        css = '[class*="wcl-shadow_"]{display:none !important}'
        for code in ("JOH", "SVA"):
            with self.subTest(team=code):
                table = self.load(f"stats_top_{code}.html", css).evaluate(JS_TABLE)
                headers = _headers(table["heads"])
                got = {"headers": headers, "rows": _records(headers, table["rows"])}
                self.assertEqual(got, self.expected["stats"]["teams"][code]["Top Stats"])
                self.assertTrue(all(r["id"] for r in table["rows"]))

    def test_lineups_lists_match_result(self):
        raw = self.load("lineups.html").evaluate(JS_LINEUPS)
        self.assertEqual([g["head"] for g in raw["groups"]],
                         ["substituted players", "starting lineups", "substitutes", "coaches"])
        built = build_lineups(raw, {}, Warnings())         # roster rỗng ⇒ tên lấy từ danh sách lineups
        for key in ("starting_xi", "substitutes", "substituted", "coaches"):
            self.assertEqual(built[key], self.expected["lineups"][key], key)
        self.assertEqual([len(r) for r in raw["formation"]["home"]], [1, 3, 4, 2, 1])
        self.assertEqual([len(r) for r in raw["formation"]["away"]], [1, 4, 2, 3, 1])
        self.assertEqual(raw["formation"]["label"], ["3 - 4 - 2 - 1", "Formation", "4 - 2 - 3 - 1"])


if __name__ == "__main__":
    unittest.main()
