"""Kiểm chứng công cụ bảo vệ match_report.html (tools/html_guard.py) — cấu hình redesign RD1–RD7.

Các sửa đổi được mô phỏng trên bản sao trong bộ nhớ — không đụng file thật.
"""
import sys
import unittest

from tests._support import ROOT

sys.path.insert(0, str(ROOT / "tools"))
import html_guard  # noqa: E402


def apply_allowed_edits(base: str) -> str:
    """Mô phỏng một lần sửa ở mỗi vùng RD của Change surface (design doc dashboard-redesign §10.1)."""
    t = base
    t = t.replace(":root{\n", ":root{\n  --brand:#C8102E;\n", 1)                                             # RD1
    t = t.replace("      <h1>Match Performance</h1>", "      <h1>Match Performance</h1><!-- rd5 -->", 1)        # RD5
    t = t.replace('  <div class="scorebar" id="scorebar"></div>',
                  '  <div class="scorebar" id="scorebar"></div>\n  <div class="nav-bar"></div>', 1)            # RD4
    start = t.index("const Render = (()=>{")
    end = t.index("  return { scorebar, tabs, activeTab, _names:TEAM_FULL };\n})();")
    t = t[:start] + "const Views = {};\nconst Render = (()=>{\n" + t[end:]                                  # RD2
    start = t.index("const Exporter = (()=>{")
    end = t.index("  return { run };\n})();", start)
    t = t[:start] + "const Report = {};\nconst Exporter = (()=>{\n  async function run(){}\n" + t[end:]        # RD3
    t = t.replace("      state.lineupText=res.lineups||null;\n",
                  "      state.lineupText=res.lineups||null;\n" + html_guard.RD7_BUILD, 1)                     # RD7
    old = "    state.lineupImages={}; state.lineupText=null; state.summary=null; state.currentTeam='all'; state.currentTab='overall';\n"
    t = t.replace(old, old + html_guard.RD7_RESET, 1)                                                     # RD7
    return t


class HtmlGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = html_guard.load_baseline()

    def frozen(self, text):
        return {n: ok for n, ok, _ in html_guard.check_frozen(self.base, text)}

    def assertFrozenOk(self, text):
        bad = [(n, d) for n, ok, d in html_guard.check_frozen(self.base, text) if not ok]
        self.assertEqual(bad, [])

    def test_baseline_is_the_redesign_tag(self):
        self.assertEqual(html_guard.baseline_rev(), html_guard.git("rev-parse", "redesign-baseline^{commit}").decode().strip())

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
        used = {e for h in hunks for e in (h.eid or "").split("+")} - {"(chỉ dòng trống)"}
        self.assertEqual(used, {"RD1", "RD2", "RD3", "RD4", "RD5", "RD7"})

    def test_change_inside_lineup_ocr_is_caught(self):
        edited = self.base.replace("function bigrams(s){", "function bigrams(s){ /*x*/", 1)
        self.assertNotEqual(edited, self.base)
        self.assertFalse(self.frozen(edited)["LineupOCR"])
        self.assertFalse(html_guard.diff_budget(self.base, edited)[0])

    def test_change_in_app_outside_rd7_is_caught(self):
        edited = self.base.replace("    destroyCharts();\n    document.getElementById('dashboard').classList.remove('active');",
                                   "    destroyCharts(); /*x*/\n    document.getElementById('dashboard').classList.remove('active');", 1)
        self.assertNotEqual(edited, self.base)
        self.assertFalse(self.frozen(edited)["core: state / TABS / U / ô URL / Api / App"])
        self.assertFalse(html_guard.diff_budget(self.base, edited)[0])

    def test_change_to_url_screen_is_caught(self):
        edited = self.base.replace("Generate report</button>", "Generate</button>", 1)
        self.assertNotEqual(edited, self.base)
        self.assertFalse(self.frozen(edited)["màn hình nhập URL"])
        self.assertFalse(html_guard.diff_budget(self.base, edited)[0])

    def test_demo_data_change_is_caught(self):
        edited = self.base.replace('window.__DEMO_STATS="{', 'window.__DEMO_STATS="{ ', 1)
        self.assertFalse(self.frozen(edited)["demo data"])

    def test_change_to_overlay_is_caught(self):
        edited = self.base.replace('<div class="toast" id="toast"></div>', '<div class="toast" id="toast" role="status"></div>', 1)
        self.assertFalse(self.frozen(edited)["loading overlay + toast"])


class CurrentFileWithinBudgetTest(unittest.TestCase):
    """Cổng thật: match_report.html hiện tại chỉ được khác baseline trong RD1–RD7."""

    def test_current_file(self):
        base, cur = html_guard.load_baseline(), html_guard.load_current()
        bad = [(n, d) for n, ok, d in html_guard.check_frozen(base, cur) if not ok]
        self.assertEqual(bad, [], "vùng đóng băng bị thay đổi")
        ok, hunks = html_guard.diff_budget(base, cur)
        outside = [(h.i1 + 1, h.removed[:2], h.added[:2]) for h in hunks if not h.eid]
        self.assertTrue(ok, f"thay đổi ngoài Change surface: {outside}")


if __name__ == "__main__":
    unittest.main()
