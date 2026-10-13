"""Kiểm chứng công cụ bảo vệ match_report.html (tools/html_guard.py).

Các sửa đổi được mô phỏng trên bản sao trong bộ nhớ — không đụng file thật.
"""
import sys
import unittest

from tests._support import ROOT

sys.path.insert(0, str(ROOT / "tools"))
import html_guard  # noqa: E402


def apply_allowed_edits(base: str) -> str:
    """Mô phỏng đủ 7 điểm sửa E1–E7 của Change surface (§7.1)."""
    t = base
    t = t.replace("<p>Drop in your two Flashscore exports — player stats and lineups — and get",
                  "<p>Paste a Flashscore match link and get", 1)                                       # E1
    start = t.index('  <div class="drop-grid">')
    end = t.index('  <div class="upload-cta">')
    t = t[:start] + '  <div class="url-form" id="urlForm">\n    <input id="flashUrl">\n  </div>\n\n' + t[end:]  # E2
    t = t.replace('id="btnBuild" onclick="App.build()" disabled>Build dashboard',
                  'id="btnGenerate" onclick="App.buildFromUrl()" disabled>Generate report', 1)            # E2
    t = t.replace("</style>", "/* url form */\n.url-form{max-width:680px}\n</style>", 1)                  # E3
    start = t.index("/* ---------- dropzones ---------- */")
    end = t.index("/* ---------- build / reset / navigation ---------- */")
    t = t[:start] + "/* ---------- URL form ---------- */\nfunction setupUrlForm(){}\n\n" + t[end:]      # E4
    t = t.replace("document.addEventListener('DOMContentLoaded',setupDropzones);",
                  "document.addEventListener('DOMContentLoaded',setupUrlForm);", 1)                   # E4
    start = t.index("  async build(){")
    end = t.index("  async loadDemo(){")
    t = t[:start] + "  async buildFromUrl(){\n    return 1;\n  },\n" + t[end:]                          # E5
    start = t.index("    document.querySelectorAll('.drop-zone')")
    end = t.index("document.getElementById('btnBuild').disabled=true;\n") + len("document.getElementById('btnBuild').disabled=true;\n")
    t = t[:start] + "    document.getElementById('flashUrl').value='';\n" + t[end:]                     # E6
    t = t.replace(html_guard.E7_OLD, html_guard.E7_NEW, 1)                                              # E7
    return t


class HtmlGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = html_guard.load_baseline()

    def assertFrozenOk(self, text):
        bad = [(n, d) for n, ok, d in html_guard.check_frozen(self.base, text) if not ok]
        self.assertEqual(bad, [])

    def test_baseline_against_itself(self):
        self.assertFrozenOk(self.base)
        ok, hunks = html_guard.diff_budget(self.base, self.base)
        self.assertTrue(ok)
        self.assertEqual(hunks, [])

    def test_all_allowed_edits_pass(self):
        edited = apply_allowed_edits(self.base)
        self.assertNotEqual(edited, self.base)
        self.assertFrozenOk(edited)
        ok, hunks = html_guard.diff_budget(self.base, edited)
        outside = [(h.i1 + 1, h.removed[:2], h.added[:2]) for h in hunks if not h.eid]
        self.assertTrue(ok, f"khối ngoài phạm vi: {outside}")
        self.assertEqual({h.eid for h in hunks} - {"(chỉ dòng trống)"},
                         {"E1", "E2", "E3", "E4", "E5", "E6", "E7"})

    def test_change_inside_render_is_caught(self):
        edited = self.base.replace("function minNum(m){", "function minNum(m){ /*x*/", 1)
        frozen = {n: ok for n, ok, _ in html_guard.check_frozen(self.base, edited)}
        self.assertFalse(frozen["Render (trừ dòng E7)"])
        ok, _ = html_guard.diff_budget(self.base, edited)
        self.assertFalse(ok)

    def test_change_to_existing_css_is_caught(self):
        edited = self.base.replace(".dashboard{display:none}", ".dashboard{display:block}", 1)
        frozen = {n: ok for n, ok, _ in html_guard.check_frozen(self.base, edited)}
        self.assertFalse(frozen["CSS hiện có"])
        self.assertFalse(html_guard.diff_budget(self.base, edited)[0])

    def test_change_outside_windows_is_caught(self):
        # Dòng `</section>` của màn hình upload không thuộc vùng đóng băng lẫn cửa sổ E nào.
        edited = self.base.replace("  </div>\n</section>", "  </div>\n</section><!-- x -->", 1)
        self.assertNotEqual(edited, self.base)
        ok, hunks = html_guard.diff_budget(self.base, edited)
        self.assertFalse(ok)
        self.assertTrue(any(h.eid is None for h in hunks))

    def test_change_in_app_reset_outside_e6_is_caught(self):
        edited = self.base.replace("    destroyCharts();\n    document.getElementById('dashboard').classList.remove('active');",
                                   "    destroyCharts(); /*x*/\n    document.getElementById('dashboard').classList.remove('active');", 1)
        self.assertNotEqual(edited, self.base)
        self.assertFalse(html_guard.diff_budget(self.base, edited)[0])

    def test_demo_data_change_is_caught(self):
        edited = self.base.replace('window.__DEMO_STATS="{', 'window.__DEMO_STATS="{ ', 1)
        frozen = {n: ok for n, ok, _ in html_guard.check_frozen(self.base, edited)}
        self.assertFalse(frozen["demo data"])


class CurrentFileWithinBudgetTest(unittest.TestCase):
    """Cổng thật: file match_report.html hiện tại chỉ được khác baseline trong E1–E7."""

    def test_current_file(self):
        base, cur = html_guard.load_baseline(), html_guard.load_current()
        bad = [(n, d) for n, ok, d in html_guard.check_frozen(base, cur) if not ok]
        self.assertEqual(bad, [], "vùng đóng băng bị thay đổi")
        ok, hunks = html_guard.diff_budget(base, cur)
        outside = [(h.i1 + 1, h.removed[:2], h.added[:2]) for h in hunks if not h.eid]
        self.assertTrue(ok, f"thay đổi ngoài Change surface: {outside}")


if __name__ == "__main__":
    unittest.main()
