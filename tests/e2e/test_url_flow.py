"""Luồng "dán link" của match_report.html qua server.py thật + runner giả (bước 3.6; checklist R-01, R-07…R-19).

Không chạm flashscore.com: runner trả dữ liệu dựng sẵn. Cần mạng cho thư viện CDN.
"""
import json
import re
import unittest

from playwright.sync_api import sync_playwright

from crawler.errors import CrawlError
from crawler.lineups import lineup_images
from tests import _support
from tests.e2e import demo_views

URL = "https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/?mid=vLuGlk0n"
MATCH_STORY = '<div class="section-title" style="margin-top:28px">Match story</div>'
FM_PLAYER = "#lc-formation .fm-player"     # điểm neo kích thước 0 (xem CSS) ⇒ chờ "attached", không phải "visible"


def demo_stats() -> dict:
    """state.data của demo, lấy từ window.__DEMO_STATS trong chính file HTML."""
    for line in _support.HTML.read_text(encoding="utf-8").split("\n"):
        if line.startswith("window.__DEMO_STATS="):
            body = line[len("window.__DEMO_STATS="):].rstrip(";")
            return json.loads(json.loads(body))
    raise AssertionError("không thấy __DEMO_STATS")


def johor_result() -> dict:
    return json.loads((_support.FIXTURES / "vLuGlk0n" / "result.json").read_text(encoding="utf-8"))


class Runner:
    def __init__(self, result=None, error: str | None = None):
        self.result, self.error, self.calls = result, error, []

    def __call__(self, url, progress):
        self.calls.append(url)
        progress({"phase": "player_stats", "done": 3, "total": 10, "message": "Reading player stats · Attack (3/7)…"})
        if self.error:
            raise CrawlError(self.error)
        return self.result


def timeline_marker_count(events: list[dict]) -> int:
    """Cùng cách nhóm marker như overallTimeline() của Render (side + minute + loại)."""
    def cat(t):
        for pattern, name in ((r"own goal", "og"), (r"goal", "goal"), (r"second yellow", "yr"), (r"red", "red"),
                              (r"yellow", "yel"), (r"sub", "sub"), (r"var", "var")):
            if re.search(pattern, t, re.I):
                return name
        return "other"
    return len({f"{e['side']}@{e['minute']}@{cat(e['type'])}" for e in events})


class UrlFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def new_page(self):
        page = self.browser.new_page(viewport={"width": 1280, "height": 900}, accept_downloads=True)
        self.addCleanup(page.close)
        _support.block_noise(page)
        log = _support.ConsoleLog(page)
        requests: list[str] = []
        page.on("request", lambda r: requests.append(r.url))
        return page, log, requests

    def generate(self, page, base, url=URL):
        page.goto(base + "/", wait_until="load")
        page.fill("#flashUrl", url)
        page.click("#btnGenerate")

    # ---- R-01: màn hình nhập ----
    def test_input_screen(self):
        with _support.running_server(Runner(demo_stats())) as base:
            page, log, _ = self.new_page()
            page.goto(base + "/", wait_until="load")
            self.assertEqual(page.locator(".drop-zone, #fileStats, #btnBuild").count(), 0)
            self.assertTrue(page.is_visible("#flashUrl"))
            self.assertTrue(page.is_disabled("#btnGenerate"))
            self.assertTrue(page.is_visible(".demo-link"))
            page.fill("#flashUrl", "hello")
            self.assertTrue(page.is_disabled("#btnGenerate"))
            page.fill("#flashUrl", URL)
            self.assertTrue(page.is_enabled("#btnGenerate"))
            self.assertEqual(log.errors, [])

    # ---- 3.6: dữ liệu demo đi qua luồng URL ⇒ dashboard trùng golden ----
    def test_demo_data_through_url_flow_matches_golden(self):
        golden = json.loads((_support.GOLDEN / "demo_views.json").read_text(encoding="utf-8"))
        result = {"stats": demo_stats(), "summary": None, "lineups": None, "lineupImages": {}, "warnings": []}
        with _support.running_server(Runner(result)) as base:
            page, log, _ = self.new_page()
            self.generate(page, base)
            page.wait_for_selector("#dashboard.active", timeout=30000)
            views = demo_views.capture_views(page)
        others = [k for k in golden if k != "all/overall"]
        self.assertEqual(demo_views.diff_views(golden, views, only=others), [])
        g, v = golden["all/overall"], views["all/overall"]
        prefix = g["html"].split(MATCH_STORY)[0]
        self.assertTrue(v["html"].startswith(prefix), "phần head-to-head/timeline của Overall khác golden")
        self.assertIn("Line-ups are not available for this match.", v["html"][len(prefix):])
        for field in ("scorebar", "charts", "tabNav", "footMatch", "buttons", "toggleDisplay"):
            self.assertEqual(v[field], g[field], field)
        self.assertEqual(log.errors, [])

    # ---- R-08…R-11: dữ liệu thật (fixture Johor DT) ----
    def test_real_match_renders_match_story_without_ocr(self):
        result = johor_result()
        with _support.running_server(Runner(result)) as base:
            page, log, requests = self.new_page()
            self.generate(page, base)
            page.wait_for_selector("#dashboard.active", timeout=30000)
            page.wait_for_selector(FM_PLAYER, state="attached")
            score = page.inner_text("#scorebar .score-line").replace("\n", "")
            self.assertEqual(re.sub(r"\s+", "", score), "6–0")
            self.assertEqual(page.locator("#scorebar img.team-logo").count(), 2)
            self.assertEqual(page.locator("#scorebar .sc-side.home .sc-goal").count(), 6)
            self.assertEqual(page.locator(".tl-ev").count(), timeline_marker_count(result["summary"]["events"]))
            self.assertEqual(page.locator("#lc-formation .fm-player").count(), 22)
            rated = page.locator("#lc-formation .fm-player .rating-badge").count()
            self.assertEqual(rated, 22, "mọi cầu thủ trên sơ đồ phải tra được rating theo tên")
            self.assertEqual(page.locator("#lc-starting tr").count(), 11)
            self.assertEqual(page.locator("#lc-substitutes tr").count(), 12)
            self.assertEqual(page.locator("#lc-coaches .ln-name").all_inner_texts(), ["Xisco", "McConkey M."])
            self.assertEqual(page.locator("#tc-overall .unverified").count(), 0)
            self.assertFalse(any("tesseract" in u for u in requests), "luồng URL không được tải OCR")
            self.assertEqual(page.evaluate("state.lineupText.starting_xi.length"), 11)
            # chuyển tab rồi quay lại Overall: Match story vẽ lại từ cache, không lỗi
            page.evaluate("App.setTab('shots')")
            page.evaluate("App.setTeam('home')")
            self.assertGreater(page.locator("#tbl-shots tbody tr").count(), 10)
            page.evaluate("App.setTeam('all'); App.setTab('overall')")
            self.assertEqual(page.locator("#lc-formation .fm-player").count(), 22)
            self.assertEqual(log.errors, [])

    @unittest.skipIf(_support.SKIP_PDF, "FS_SKIP_PDF=1")
    def test_real_match_export_pdf(self):
        with _support.running_server(Runner(johor_result())) as base:
            page, log, _ = self.new_page()
            self.generate(page, base)
            page.wait_for_selector(FM_PLAYER, state="attached", timeout=30000)
            with page.expect_download(timeout=240000) as dl:
                page.click("#btnExport")
            target = _support.output_dir() / "url_flow_report.pdf"
            dl.value.save_as(target)
            self.assertTrue(target.read_bytes().startswith(b"%PDF"))
            self.assertEqual(dl.value.suggested_filename, "MatchReport_Johor_DT_vs_Svay_Rieng.pdf")
            self.assertEqual(log.errors, [])

    # ---- R-07 / R-19: New match rồi trận khác ----
    def test_new_match_then_another_match(self):
        with _support.running_server(Runner(johor_result())) as base:
            page, log, _ = self.new_page()
            self.generate(page, base)
            page.wait_for_selector(FM_PLAYER, state="attached", timeout=30000)
            page.click("#btnReset")
            self.assertEqual(page.eval_on_selector("#uploadScreen", "e => e.style.display"), "flex")
            self.assertEqual(page.input_value("#flashUrl"), "")
            self.assertTrue(page.is_disabled("#btnGenerate"))
            self.assertIsNone(page.evaluate("state.lineupText"))
            page.click(".demo-link")                   # demo sau luồng URL: OCR path, không rò lineupText
            page.wait_for_selector("#dashboard.active")
            self.assertEqual(page.evaluate("state.data.home"), "KOR")
            self.assertEqual(page.locator("#tc-overall #lc-formation").count(), 1)
            self.assertEqual(log.errors, [])

    # ---- R-12: link sai không gọi server ----
    def test_invalid_link_shows_inline_error_without_request(self):
        with _support.running_server(Runner(johor_result())) as base:
            page, log, requests = self.new_page()
            page.goto(base + "/", wait_until="load")
            page.fill("#flashUrl", "https://example.com/not-a-match")
            page.press("#flashUrl", "Enter")
            self.assertIn("Paste a Flashscore football match link", page.inner_text("#urlError"))
            self.assertFalse(any("/api/matches" in u for u in requests))
            page.fill("#flashUrl", URL)                # gõ lại ⇒ lỗi biến mất
            self.assertEqual(page.inner_text("#urlError"), "")
            self.assertEqual(log.errors, [])

    # ---- R-14: lỗi từ crawler hiển thị rõ ----
    def test_crawler_error_is_shown(self):
        with _support.running_server(Runner(error="E_MATCH_NOT_FINISHED")) as base:
            page, log, _ = self.new_page()
            self.generate(page, base)
            page.wait_for_function("document.getElementById('urlError').textContent.length > 0", timeout=30000)
            self.assertIn("has not finished", page.inner_text("#urlError"))
            self.assertFalse(page.eval_on_selector("#dashboard", "e => e.classList.contains('active')"))
            self.assertFalse(page.eval_on_selector("#loading", "e => e.classList.contains('show')"))

    # ---- R-13: server không phản hồi ----
    def test_unreachable_server_message(self):
        with _support.running_server(Runner(johor_result())) as base:
            page, log, _ = self.new_page()
            page.route("**/api/matches", lambda route: route.abort())
            self.generate(page, base)
            page.wait_for_function("document.getElementById('urlError').textContent.length > 0", timeout=30000)
            self.assertIn("Cannot reach the local server", page.inner_text("#urlError"))

    # ---- R-16: cảnh báo hiển thị bằng toast, dashboard vẫn dựng ----
    def test_warning_toast(self):
        result = johor_result()
        result["warnings"] = [{"code": "W_NO_MID", "message": "The link has no ?mid= part."}]
        with _support.running_server(Runner(result)) as base:
            page, log, _ = self.new_page()
            self.generate(page, base)
            page.wait_for_selector("#dashboard.active", timeout=30000)
            page.wait_for_selector("#toast.show")
            self.assertIn("no ?mid= part", page.inner_text("#toast"))

    # ---- R-18: mở bằng file:// ----
    def test_file_protocol_demo_still_works_and_generate_explains(self):
        page, log, _ = self.new_page()
        page.goto(_support.HTML.as_uri(), wait_until="load")
        page.fill("#flashUrl", URL)
        page.click("#btnGenerate")
        page.wait_for_function("document.getElementById('urlError').textContent.length > 0", timeout=30000)
        self.assertIn("Cannot reach the local server", page.inner_text("#urlError"))
        page.click(".demo-link")
        page.wait_for_selector("#dashboard.active")
        self.assertEqual(page.evaluate("state.data.home"), "KOR")

    def test_placeholder_invariant_in_fixture(self):
        result = johor_result()
        self.assertEqual(result["lineupImages"], lineup_images(result["lineups"]))


if __name__ == "__main__":
    unittest.main()
