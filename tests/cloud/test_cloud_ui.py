"""e2e trình duyệt cho bản cloud (design doc cloud §11, §14): đăng nhập → thư viện → dán link → /m/{mid};
link chia sẻ ẩn danh; luồng /report qua Api đóng băng (+ CSRF do khối RD8 thêm); PDF và demo OCR dưới CSP.

Cần mạng cho CDN (Chart.js, jsPDF, html2canvas; Tesseract cho test demo). FS_SKIP_PDF=1 bỏ test PDF.
"""
import re
import unittest

from tests import _support
from tests.cloud._harness import CLOUD_DEPS, LINKS, PASSWORD, CloudServer

if CLOUD_DEPS:
    from playwright.sync_api import sync_playwright


@unittest.skipUnless(CLOUD_DEPS, "cần pip install -r requirements-cloud.txt")
class CloudUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def page(self, block_ocr: bool = True):
        ctx = self.browser.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        if block_ocr:
            _support.block_noise(page)
        log = _support.ConsoleLog(page)
        csp: list[str] = []
        page.on("console", lambda m: "Content Security Policy" in m.text and csp.append(m.text))
        return page, log, csp

    def sign_in(self, page, base, email):
        page.goto(base + "/#/login", wait_until="load")
        page.fill("#email", email)
        page.fill("#pw", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_selector("#fNew")

    def test_library_flow_share_link_and_report_page(self):
        with CloudServer(background_worker=True) as srv:
            srv.admin("admin@example.com")
            page, log, csp = self.page()
            page.goto(srv.base + "/m/vLuGlk0n", wait_until="load")
            page.wait_for_url(re.compile(r"/#/login\?next="))                 # chưa đăng nhập ⇒ về trang đăng nhập
            page.fill("#email", "admin@example.com")
            page.fill("#pw", PASSWORD)
            page.click("button[type=submit]")
            page.wait_for_url(srv.base + "/m/vLuGlk0n")                       # quay lại đúng trang đã yêu cầu
            page.wait_for_function("document.getElementById('urlError').textContent.includes('not in the library')")
            page.click("#btnLibrary")
            page.wait_for_selector("#fNew")
            self.assertIn("No daily limit", page.inner_text("#view"))
            page.fill("#url", LINKS["vLuGlk0n"])
            page.click("#btnGo")
            page.wait_for_url(srv.base + "/m/vLuGlk0n", timeout=30000)
            page.wait_for_selector("#dashboard.active", timeout=30000)
            self.assertEqual(re.sub(r"\s+", "", page.inner_text("#scorebar .score-line")), "6–0")
            self.assertTrue(page.is_visible("#btnLibrary"))
            page.evaluate("App.setTab('overall')")
            page.wait_for_selector("#lc-formation .fm-player", state="attached")
            # thư viện liệt kê trận; bật link chia sẻ
            page.click("#btnLibrary")
            page.wait_for_selector("#list tbody tr")
            self.assertIn("Johor DT", page.inner_text("#list"))
            page.once("dialog", lambda d: d.accept())
            page.click("#list button[data-act=share]")
            page.wait_for_selector("#list button[data-act=share]:has-text('Shared')")   # CSP trang thư viện cấm eval
            conn = srv.conn()
            token = conn.execute("SELECT share_token FROM matches WHERE match_key = 'vLuGlk0n'").fetchone()[0]
            conn.close()
            self.assertEqual(log.errors, [])
            self.assertEqual(csp, [])
            # người xem ẩn danh mở link chia sẻ: xem được, không có nút New match
            anon, alog, acsp = self.page()
            anon.goto(f"{srv.base}/m/vLuGlk0n?s={token}", wait_until="load")
            anon.wait_for_selector("#dashboard.active", timeout=30000)
            self.assertEqual(anon.locator("#btnReset").count(), 0)
            self.assertEqual(re.sub(r"\s+", "", anon.inner_text("#scorebar .score-line")), "6–0")
            anon.goto(f"{srv.base}/m/vLuGlk0n?s=wrong-token", wait_until="load")
            anon.wait_for_url(re.compile(r"/#/login"))
            self.assertEqual(alog.errors, [])
            self.assertEqual(acsp, [])

    def test_report_page_paste_link_uses_frozen_api_with_csrf(self):
        with CloudServer(background_worker=True) as srv:
            srv.member("coach@example.com")
            page, log, csp = self.page()
            self.sign_in(page, srv.base, "coach@example.com")
            page.goto(srv.base + "/report", wait_until="load")
            page.wait_for_selector("#btnLibrary")                              # khối RD8 đã kích hoạt
            page.fill("#flashUrl", LINKS["GGiPsLP1"])
            page.click("#btnGenerate")
            page.wait_for_selector("#dashboard.active", timeout=30000)
            page.wait_for_url(srv.base + "/m/GGiPsLP1")
            self.assertEqual(re.sub(r"\s+", "", page.inner_text("#scorebar .score-line")), "1–3")
            page.click("#btnReset")                                            # New match ⇒ quay lại /report
            page.wait_for_url(srv.base + "/report")
            self.assertTrue(page.is_visible("#flashUrl"))
            self.assertEqual(log.errors, [])
            self.assertEqual(csp, [])

    @unittest.skipIf(_support.SKIP_PDF, "FS_SKIP_PDF=1")
    def test_pdf_export_works_under_csp(self):
        with CloudServer(background_worker=True) as srv:
            srv.member("coach@example.com")
            page, log, csp = self.page()
            self.sign_in(page, srv.base, "coach@example.com")
            page.fill("#url", LINKS["tW4rOkzg"])
            page.click("#btnGo")
            page.wait_for_selector("#dashboard.active", timeout=30000)
            with page.expect_download(timeout=240000) as dl:
                page.click("#btnExportMenu")
                page.click("#exportMenu button:has-text('Coach brief')")
            data = dl.value.path().read_bytes()
            self.assertTrue(data.startswith(b"%PDF"))
            self.assertEqual(len(re.findall(rb"/Type\s*/Page[^s]", data)), 4)
            self.assertEqual(log.errors, [])
            self.assertEqual(csp, [])

    def test_demo_ocr_works_under_csp(self):
        with CloudServer() as srv:
            page, log, csp = self.page(block_ocr=False)                         # Tesseract cần tải từ CDN
            page.goto(srv.base + "/report", wait_until="load")
            page.wait_for_url(re.compile(r"/#/login"))                         # /report cũng cần đăng nhập
            srv.member("demo@example.com")
            self.sign_in(page, srv.base, "demo@example.com")
            page.goto(srv.base + "/report", wait_until="load")
            page.click(".demo-link")
            page.wait_for_selector("#dashboard.active")
            page.evaluate("App.setTab('overall')")
            page.wait_for_function("state.lineupText !== null", timeout=240000)
            self.assertEqual(page.evaluate("state.lineupText.formation.players.length"), 22)
            self.assertEqual(log.errors, [])
            self.assertEqual(csp, [])

    def test_admin_approves_new_account(self):
        with CloudServer() as srv:
            srv.admin("admin@example.com")
            reg, _, _ = self.page()
            reg.goto(srv.base + "/#/register", wait_until="load")
            reg.fill("#email", "new@example.com")
            reg.fill("#pw", PASSWORD)
            reg.fill("#pw2", PASSWORD)
            reg.click("button[type=submit]")
            reg.wait_for_selector("text=Check your inbox")
            from tests.cloud._harness import last_link_token
            reg.goto(srv.base + "/#/verify/" + last_link_token("new@example.com", "verify"), wait_until="load")
            reg.wait_for_selector("text=An administrator will approve")
            page, log, csp = self.page()
            page.goto(srv.base + "/#/login", wait_until="load")
            page.fill("#email", "admin@example.com")
            page.fill("#pw", PASSWORD)
            page.click("button[type=submit]")
            page.wait_for_selector("#fNew")
            page.goto(srv.base + "/#/admin", wait_until="load")
            page.wait_for_selector("#users tbody tr")
            row = page.locator("#users tr", has_text="new@example.com")
            self.assertIn("waiting for approval", row.inner_text())
            row.locator("button[data-act=approve]").click()
            page.locator("#users tr", has_text="new@example.com").locator(".tag.pos").wait_for()
            self.assertEqual(log.errors, [])
            self.assertEqual(csp, [])


if __name__ == "__main__":
    unittest.main()
