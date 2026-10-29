"""Dashboard + PDF thiết kế lại (design doc dashboard-redesign §10.2, §12): hợp đồng hành vi B5–B8,
đồng nhất font/cỡ chữ/màu chữ, số liệu Metrics/Insights so với Flashscore, menu Export và số trang PDF.

Dữ liệu nạp thẳng vào `state` từ fixture result.json rồi gọi App.enter() — không cần server.
Cần mạng cho thư viện CDN (Chart.js, jsPDF, html2canvas). FS_SKIP_PDF=1 bỏ test PDF.
"""
import json
import re
import unittest

from playwright.sync_api import sync_playwright

from tests import _support

MIDS = ("vLuGlk0n", "GGiPsLP1", "d8pxv90m", "tW4rOkzg")
VIEWS = ["summary", "team", "attack", "passing", "defending", "goalkeeping", "players", "overall"]
FILTER_VIEWS = {"attack", "passing", "defending", "players"}

ENTER_JS = """(r) => {
  state.data=r.stats; state.summary=r.summary||null; state.lineupImages=r.lineupImages||{}; state.lineupText=r.lineups||null;
  state.teamStats=r.teamStats||null; state.meta=r.meta||null; App.enter();
}"""

# §12.3 — chỉ những giá trị này được phép cho chữ hiển thị
ALLOWED_SIZES = {12.0, 14.0, 18.0, 22.0, 24.0, 40.0}
ALLOWED_SIZES_MOBILE = ALLOWED_SIZES | {32.0}
ALLOWED_COLORS = {
    "rgb(17, 24, 39)", "rgb(55, 65, 81)", "rgb(107, 114, 128)",   # ink, ink-2, ink-3
    "rgb(200, 16, 46)", "rgb(255, 255, 255)",                       # brand, white on red/dark
    "rgb(21, 128, 61)", "rgb(180, 83, 9)",                          # pos, neg
    "rgb(20, 83, 45)", "rgb(146, 64, 14)",                          # rating-good / rating-poor text
}
TYPO_JS = """() => {
  const out=[];
  for (const el of document.querySelectorAll('#dashboard *, .app-header *')) {
    const own=[...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim());
    if(!own||!el.getClientRects().length) continue;
    const cs=getComputedStyle(el);
    if(cs.visibility==='hidden'||+cs.opacity===0) continue;
    if(el.closest('.tl-tip')) continue;                          // tooltip ẩn (opacity 0 ở cha)
    out.push({tag:el.tagName,cls:String(el.className).slice(0,40),text:el.textContent.trim().slice(0,30),
      size:parseFloat(cs.fontSize),color:cs.color,family:cs.fontFamily});
  }
  return out;
}"""


def result(mid: str) -> dict:
    return json.loads((_support.FIXTURES / mid / "result.json").read_text(encoding="utf-8"))


def fs_value(res: dict, scope: str, key: str, side: str) -> float:
    rows = res["teamStats"][scope]["rows"]
    row = (next((r for r in rows if r["key"] == key and r["group"] != "Top stats"), None)
           or next(r for r in rows if r["key"] == key))
    return float(re.sub(r"[^0-9.\-]", "", row[side]))


class RedesignTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def open(self, mid: str | None, width: int = 1280):
        page = self.browser.new_page(viewport={"width": width, "height": 900}, accept_downloads=True)
        self.addCleanup(page.close)
        _support.block_noise(page)
        log = _support.ConsoleLog(page)
        page.goto(_support.HTML.as_uri(), wait_until="load")
        page.wait_for_function("typeof App !== 'undefined' && typeof Chart !== 'undefined'")
        if mid is None:
            page.evaluate("App.loadDemo()")
        else:
            page.evaluate(ENTER_JS, result(mid))
        page.wait_for_selector("#dashboard.active", timeout=15000)
        return page, log

    # ---- B7 / B8: mọi tab × bộ lọc, 2 khổ màn hình: không lỗi JS, không cuộn ngang toàn trang ----
    def test_all_views_render_without_errors_or_horizontal_scroll(self):
        for mid in (None,) + MIDS:
            for width in (1280, 420):
                with self.subTest(match=mid or "demo", width=width):
                    page, log = self.open(mid, width)
                    for view in VIEWS:
                        for team in (("all", "home", "away") if view in FILTER_VIEWS else ("all",)):
                            page.evaluate(f"App.setTeam('{team}'); App.setTab('{view}')")
                            self.assertTrue(page.evaluate(f"document.getElementById('tc-{view}').innerHTML.length > 100"), view)
                            self.assertFalse(page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"),
                                             f"cuộn ngang ở {view}/{team}")
                    self.assertEqual(log.errors, [])

    # ---- §12.3: đồng nhất font / cỡ chữ / màu chữ ----
    def test_typography_is_consistent(self):
        for width, sizes in ((1280, ALLOWED_SIZES), (420, ALLOWED_SIZES_MOBILE)):
            with self.subTest(width=width):
                page, _ = self.open("vLuGlk0n", width)
                bad = []
                for view in VIEWS:
                    page.evaluate(f"App.setTeam('all'); App.setTab('{view}')")
                    if view == "players":
                        page.click("#tbl-players tbody tr.clickable")
                    for t in page.evaluate(TYPO_JS):
                        if t["size"] not in sizes or t["color"] not in ALLOWED_COLORS or not t["family"].startswith("Inter"):
                            bad.append((view, t))
                self.assertEqual(bad[:10], [], f"{len(bad)} phần tử chữ ngoài design system")

    # ---- B6: sort bảng ----
    def test_tables_sort_desc_then_asc(self):
        page, log = self.open("vLuGlk0n")
        page.evaluate("App.setTab('players')")
        minutes = lambda: [int(x) for x in page.locator("#tbl-players tbody tr.clickable td:nth-child(4)").all_inner_texts()]
        ratings = [float(x) for x in page.locator("#tbl-players tbody tr.clickable td:nth-child(5)").all_inner_texts() if x != "–"]
        self.assertEqual(ratings, sorted(ratings, reverse=True))           # mặc định: rating giảm dần
        page.click("#tbl-players th[data-col='min']")
        self.assertEqual(minutes(), sorted(minutes(), reverse=True))
        page.click("#tbl-players th[data-col='min']")
        self.assertEqual(minutes(), sorted(minutes()))
        self.assertEqual(page.get_attribute("#tbl-players th[data-col='min']", "aria-sort"), "ascending")
        page.evaluate("App.setTab('attack')")
        page.click("#tbl-shots th[data-col='Total shots']")
        shots = [int(x) if x != "-" else 0 for x in page.locator("#tbl-shots tbody tr td:nth-child(4)").all_inner_texts()]
        self.assertEqual(shots, sorted(shots, reverse=True))
        self.assertEqual(log.errors, [])

    def test_player_profile_and_filters(self):
        page, log = self.open("vLuGlk0n")
        page.evaluate("App.setTab('players')")
        self.assertEqual(page.locator("#tbl-players tbody tr.clickable").count(), 32)
        page.click("#pfGroup .chip-btn[data-group='GK']")
        self.assertEqual(page.locator("#tbl-players tbody tr.clickable").count(), 2)
        page.click("#pfGroup .chip-btn[data-group='all']")
        page.fill("#pfSearch", "Aiman")
        page.click("#tbl-players tbody tr.clickable")
        self.assertIn("Aiman A.", page.inner_text(".pp-head"))
        self.assertIn("Scored 1 goal", page.inner_text(".pp"))
        self.assertTrue(page.evaluate("!!state.charts['pp-radar']"))
        page.evaluate("App.setTeam('away')")
        self.assertEqual(page.locator("#tbl-players tbody tr.clickable").count(), 0)   # Aiman là cầu thủ đội nhà
        self.assertEqual(log.errors, [])

    # ---- số liệu: Metrics ưu tiên team stats của Flashscore, khớp với nguồn ----
    def test_metrics_match_flashscore_team_stats(self):
        keys = {"xg": "Expected goals (xG)", "shots": "Total shots", "corners": "Corner kicks",
                "passes": "Passes", "prevented": "Goals prevented", "bigChances": "Big chances"}
        for mid in MIDS:
            with self.subTest(match=mid):
                res = result(mid)
                page, _ = self.open(mid)
                for metric, key in keys.items():
                    for side in ("home", "away"):
                        got = page.evaluate(f"Metrics.team('{metric}','{side}').v")
                        self.assertAlmostEqual(got, fs_value(res, "overall", key, side), places=2, msg=f"{metric} {side}")
                        h1 = page.evaluate(f"Metrics.team('{metric}','{side}','firstHalf').v")
                        self.assertAlmostEqual(h1, fs_value(res, "firstHalf", key, side), places=2)
                fs = res["summary"]["finalScore"]
                self.assertEqual(page.evaluate("[Metrics.goalsFor('home'),Metrics.goalsFor('away')]"), [fs["h"], fs["a"]])
                reliable = res["teamStats"]["possessionReliable"]
                self.assertEqual(page.evaluate("Metrics.team('possession','home').v") is not None, reliable)
                # tổng player stats gần khớp số cấp đội (kiểm tra chéo §4.2)
                self.assertLess(abs(page.evaluate("Metrics.TEAM.xg.derive('home')") - fs_value(res, "overall", "Expected goals (xG)", "home")), 0.15)

    def test_metrics_without_team_stats_fall_back_to_player_sums(self):
        page, _ = self.open(None)                                   # demo: không có team stats
        self.assertFalse(page.evaluate("Metrics.hasTeamStats()"))
        self.assertEqual(page.evaluate("Metrics.team('corners','home').v"), None)
        self.assertEqual(page.evaluate("Metrics.team('possession','home').v"), None)
        self.assertEqual(page.evaluate("Metrics.team('shots','home').src"), "derived")
        self.assertEqual(page.evaluate("Insights.notes().map(n=>n.id)"), ["I20"])
        # không có số liệu theo hiệp ⇒ không có card Half by half rỗng (Summary lẫn Team)
        self.assertNotIn("Half by half", page.inner_text("#tc-summary"))
        page.evaluate("App.setTab('team')")
        self.assertNotIn("Half by half", page.inner_text("#tc-team"))

    def test_player_profiles(self):
        page, _ = self.open("vLuGlk0n")
        self.assertEqual(page.evaluate("Metrics.players().length"), 32)
        p = page.evaluate("""(() => { const p=Metrics.players().find(x=>x.name==='Aiman A.');
          return {group:p.group, minutes:p.v.minutes, goals:p.v.goals, assists:p.v.assists, passes:[p.v.passes,p.v.passesAtt],
                  xgP90:+p.p90.xg.toFixed(3), started:p.started, subOff:p.subOff, events:p.events.map(e=>e.kind)}; })()""")
        self.assertEqual(p, {"group": "DEF", "minutes": 78, "goals": 1, "assists": 1, "passes": [23, 30],
                             "xgP90": round(0.60 / 78 * 90, 3), "started": True, "subOff": "78'",
                             "events": ["goal", "assist", "off"]})
        sub = page.evaluate("(() => { const p=Metrics.players().find(x=>x.name==='Aketxe A.'); return [p.started,p.subOn]; })()")
        self.assertEqual(sub, [False, "67'"])
        groups = page.evaluate("[...new Set(Metrics.players().map(p=>p.group))].sort()")
        self.assertEqual(groups, ["DEF", "FWD", "GK", "MID"])
        # thứ hạng chỉ tính cầu thủ cùng nhóm, ≥ 30 phút
        ok = page.evaluate("""Metrics.players().every(p => Object.values(p.rank).every(r => r.pos>=1 && r.pos<=r.of)
          && (p.v.minutes>=30 || Object.keys(p.rank).length===0))""")
        self.assertTrue(ok)

    def test_profile_radar_compares_with_group_average(self):
        page, log = self.open("tW4rOkzg")
        page.evaluate("App.setTab('players')")
        page.fill("#pfSearch", "Willock")
        page.click("#tbl-players tbody tr.clickable")
        radar = page.evaluate("""(() => { const c=state.charts['pp-radar'];
          return {labels:c.data.labels, sets:c.data.datasets.map(d=>({label:d.label, data:d.data}))}; })()""")
        self.assertEqual([d["label"] for d in radar["sets"]], ["Willock J.", "MID average"])
        for d in radar["sets"]:
            self.assertTrue(all(0 <= x <= 100 for x in d["data"]), d)
        avg = radar["sets"][1]["data"]
        self.assertGreater(len(set(avg)), 1, "đường trung bình phải là dữ liệu thật, không phải vòng cố định")
        # trục Duels won %: Willock 2/7 = 29% là thấp nhất nhóm ⇒ 0
        self.assertEqual(radar["sets"][0]["data"][radar["labels"].index("Duels won %")], 0)
        self.assertEqual(log.errors, [])

    def test_header_has_no_logo(self):
        page, _ = self.open("vLuGlk0n")
        self.assertEqual(page.locator(".app-header .brand-mark, .app-header svg circle").count(), 0)
        self.assertEqual(page.inner_text(".brand-text h1"), "Match Performance")

    def test_report_layout_fits_the_page(self):
        """Mọi bảng nằm trong card của nó, không trang nào bị cắt nội dung, ô tên không dùng inset box-shadow
        (html2canvas tô kín ô ⇒ chữ đen trên nền đen)."""
        for mid in MIDS:
            with self.subTest(match=mid):
                page, log = self.open(mid)
                res = page.evaluate("""() => { const root=document.createElement('div'); root.id='reportRoot'; document.body.appendChild(root);
                  const pages=Report.layout(root, Report.pageDefs('full'));
                  const over=[...root.querySelectorAll('table')].filter(t=>t.getBoundingClientRect().right>(t.closest('.card')||t.closest('.pdf-page')).getBoundingClientRect().right+1).length;
                  const cut=pages.filter(p=>{const b=p.el.querySelector('.pdf-body');return b.scrollHeight>b.clientHeight+1;}).length;
                  const inset=[...root.querySelectorAll('td')].filter(td=>getComputedStyle(td).boxShadow.includes('inset')).length;
                  const pname=[...root.querySelectorAll('td.pname')].map(td=>getComputedStyle(td).backgroundColor);
                  root.remove(); return {n:pages.length, over, cut, inset, dark:pname.filter(c=>c==='rgb(31, 41, 55)'||c==='rgb(200, 16, 46)').length}; }""")
                self.assertEqual(res["over"], 0)
                self.assertEqual(res["cut"], 0)
                self.assertEqual(res["inset"], 0)
                self.assertEqual(res["dark"], 0)
                self.assertLessEqual(res["n"], 14)
                self.assertEqual(log.errors, [])

    def test_insights(self):
        page, _ = self.open("vLuGlk0n")
        ids = page.evaluate("Insights.pick().map(i=>i.id)")
        self.assertTrue({"I01", "I03", "I04", "I12", "I17"} <= set(ids), ids)
        self.assertLessEqual(len(ids), 6)
        self.assertEqual(page.evaluate("Insights.notes().map(i=>i.id)"), ["I20"])     # possession 50/50 ⇒ không tin cậy
        text = page.inner_text("#tc-summary .insights")
        self.assertIn("4.79", text)
        self.assertIn("Possession is not provided", text)
        page, _ = self.open("GGiPsLP1")
        ids = page.evaluate("Insights.all().map(i=>i.id)")
        self.assertIn("I08", ids)                                                     # possession thật 37/63
        self.assertEqual(page.evaluate("Insights.notes()"), [])

    def test_lineups_view_and_substitutions(self):
        page, log = self.open("vLuGlk0n")
        page.evaluate("App.setTab('overall')")
        page.wait_for_selector("#lc-formation .fm-player", state="attached")
        self.assertEqual(page.locator("#lu-subs .sub-item").count(), 10)
        self.assertEqual(page.locator("#lc-starting tr").count(), 11)
        self.assertEqual(log.errors, [])

    # ---- export menu + PDF ----
    def test_export_menu_opens_and_closes(self):
        page, _ = self.open("vLuGlk0n")
        self.assertTrue(page.is_visible("#btnExportMenu"))
        page.click("#btnExportMenu")
        self.assertTrue(page.is_visible("#exportMenu"))
        self.assertEqual(page.get_attribute("#btnExportMenu", "aria-expanded"), "true")
        page.click("#scorebar")
        self.assertFalse(page.is_visible("#exportMenu"))
        page.click("#btnReset")
        self.assertFalse(page.is_visible("#btnExportMenu"))                           # theo nút Export

    @unittest.skipIf(_support.SKIP_PDF, "FS_SKIP_PDF=1")
    def test_pdf_presets(self):
        page, log = self.open("GGiPsLP1")
        page.evaluate("App.setTab('passing')")
        for preset, label, pages in (("coach", "Coach brief", (4, 4)), ("full", "Full analyst report", (8, 14))):
            with self.subTest(preset=preset):
                with page.expect_download(timeout=240000) as dl:
                    page.click("#btnExportMenu")
                    page.click(f"#exportMenu button:has-text('{label}')")
                target = _support.output_dir() / f"redesign_{preset}.pdf"
                dl.value.save_as(target)
                data = target.read_bytes()
                n = len(re.findall(rb"/Type\s*/Page[^s]", data))
                self.assertTrue(pages[0] <= n <= pages[1], f"{preset}: {n} trang")
                self.assertLess(len(data), 6_000_000)
                self.assertEqual(dl.value.suggested_filename, f"MatchReport_Malaga_Villarreal_2026-09-18_{preset}.pdf")
        self.assertEqual(page.evaluate("state.currentTab"), "passing")                # B5: khôi phục tab
        self.assertEqual(page.locator("#reportRoot").count(), 0)
        self.assertEqual(log.errors, [])


if __name__ == "__main__":
    unittest.main()
