"""E2E thật: dán link trận #1 vào giao diện → server.py → crawler → dashboard (bước 3.7).

FS_LIVE=1 python -m unittest tests.live.test_live_ui   (ảnh chụp lưu ở tests/output/)
"""
import unittest

from playwright.sync_api import sync_playwright

from tests import _support

URL = "https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/?mid=vLuGlk0n"


@unittest.skipUnless(_support.LIVE, "đặt FS_LIVE=1 để chạy test chạm flashscore.com")
class LiveUiTest(unittest.TestCase):
    def test_paste_link_to_dashboard(self):
        out = _support.output_dir()
        with _support.running_server() as base, sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                log = _support.ConsoleLog(page)
                page.goto(base + "/", wait_until="networkidle")
                page.screenshot(path=str(out / "live_input_1280.png"))
                page.set_viewport_size({"width": 420, "height": 900})
                page.screenshot(path=str(out / "live_input_420.png"))
                page.set_viewport_size({"width": 1280, "height": 900})

                page.fill("#flashUrl", URL)
                page.click("#btnGenerate")
                page.wait_for_selector("#loading.show")
                messages = set()
                for _ in range(300):                       # ghi lại các thông điệp tiến độ trên overlay
                    if page.locator("#dashboard.active").count():
                        break
                    messages.add(page.inner_text("#loadingMsg"))
                    page.wait_for_timeout(500)
                page.wait_for_selector("#dashboard.active", timeout=150000)
                page.wait_for_selector("#lc-formation .fm-player", state="attached")
                page.wait_for_timeout(800)                 # để biểu đồ vẽ xong trước khi chụp
                page.screenshot(path=str(out / "live_overall.png"), full_page=True)

                self.assertTrue(any("Reading player stats" in m for m in messages), messages)
                self.assertEqual(page.locator("#lc-formation .fm-player").count(), 22)
                self.assertEqual(page.locator("#scorebar .sc-goal").count(), 6)
                self.assertGreater(page.locator(".tl-ev").count(), 10)
                page.evaluate("App.setTeam('home'); App.setTab('passes')")
                page.wait_for_timeout(600)
                page.screenshot(path=str(out / "live_passes_home.png"), full_page=True)
                self.assertEqual(page.locator("#tbl-passes tbody tr").count(), 16)
                self.assertEqual(log.errors, [])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
