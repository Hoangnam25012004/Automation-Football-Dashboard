"""Luồng demo phải giữ nguyên hành vi (checklist R-02…R-07, design doc §9.7).

Cần mạng để tải thư viện CDN. Đặt FS_SKIP_PDF=1 để bỏ qua test Export PDF (chậm).
"""
import json
import unittest

from playwright.sync_api import sync_playwright

from tests import _support
from tests.e2e import demo_views


class DemoFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def open_demo(self):
        page = self.browser.new_page(viewport={"width": 1280, "height": 900}, accept_downloads=True)
        self.addCleanup(page.close)
        _support.block_noise(page)
        log = _support.ConsoleLog(page)
        demo_views.open_dashboard_from_demo(page, _support.HTML.as_uri())
        return page, log

    def test_demo_views_match_golden(self):
        golden = json.loads((_support.GOLDEN / "demo_views.json").read_text(encoding="utf-8"))
        page, log = self.open_demo()
        views = demo_views.capture_views(page)
        self.assertEqual(demo_views.diff_views(golden, views), [])
        self.assertEqual(log.errors, [])

    def test_new_match_resets_cleanly(self):
        page, log = self.open_demo()
        page.click("#btnReset")
        self.assertEqual(page.eval_on_selector("#uploadScreen", "e => e.style.display"), "flex")
        self.assertFalse(page.eval_on_selector("#dashboard", "e => e.classList.contains('active')"))
        self.assertEqual(page.eval_on_selector("#btnReset", "e => e.style.display"), "none")
        self.assertEqual(page.eval_on_selector("#btnExport", "e => e.style.display"), "none")
        self.assertEqual(page.evaluate("state.data"), None)
        # Nút chính của màn hình nhập (cũ: #btnBuild, mới: #btnGenerate) phải bị vô hiệu sau reset.
        self.assertTrue(page.evaluate("(document.getElementById('btnGenerate') || document.getElementById('btnBuild')).disabled"))
        # Mở lại demo sau reset vẫn chạy (không rò state).
        page.evaluate("App.loadDemo()")
        page.wait_for_selector("#dashboard.active")
        self.assertEqual(page.evaluate("state.data.home"), "KOR")
        self.assertEqual(log.errors, [])

    @unittest.skipIf(_support.SKIP_PDF, "FS_SKIP_PDF=1")
    def test_export_pdf(self):
        page, log = self.open_demo()
        with page.expect_download(timeout=240000) as dl:
            page.click("#btnExport")
        target = _support.output_dir() / "demo_report.pdf"
        dl.value.save_as(target)
        data = target.read_bytes()
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertGreater(len(data), 100_000)
        self.assertTrue(dl.value.suggested_filename.startswith("MatchReport_"))
        self.assertEqual(log.errors, [])


if __name__ == "__main__":
    unittest.main()
