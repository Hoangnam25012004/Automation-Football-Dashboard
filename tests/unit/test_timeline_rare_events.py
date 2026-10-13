"""Sự kiện hiếm trong timeline + trạng thái kết thúc (U1, U2, U5 — kiểm chứng ở Phase 4).

Fixture chụp từ trang thật 2026-10-09 bằng: python tools/capture_fixtures.py --timeline-only <link…>
"""
import unittest

from playwright.sync_api import sync_playwright

from crawler.header import FINISHED, JS_HEADER
from crawler.timeline import GOAL_TYPES, JS_TIMELINE
from tests import _support


def find(events, **kv):
    return [e for e in events if all(e.get(k) == v for k, v in kv.items())]


class RareEventsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)
        cls.page = cls.browser.new_page()
        cls.page.route("**/*", lambda route: route.abort())

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def run_fixture(self, mid: str):
        folder = _support.FIXTURES / mid
        self.page.set_content("<!doctype html><html><body>" + (folder / "header.html").read_text(encoding="utf-8")
                              + (folder / "timeline.html").read_text(encoding="utf-8") + "</body></html>")
        return self.page.evaluate(JS_HEADER), self.page.evaluate(JS_TIMELINE)["events"]

    def test_penalty_shootout_after_90_minutes(self):          # Peterborough 3-3 Barnsley (PEN 7-6), EFL Cup
        header, events = self.run_fixture("rJi7Md3T")
        self.assertRegex(header["status"].strip(), FINISHED)    # "After 90 minutes" là trận ĐÃ kết thúc
        self.assertEqual(find(events, half="Penalties"), [])     # loạt luân lưu không vào timeline
        self.assertFalse(any(e["minute"] in {str(i) for i in range(1, 12)} for e in events))
        self.assertEqual(sum(e["type"] in GOAL_TYPES for e in events), 6)   # 3-3 trong 90 phút

    def test_extra_time_then_penalties(self):                  # Altglienicke 3-3 Wolfsburg (PEN 5-6), DFB-Pokal
        header, events = self.run_fixture("d8pxv90m")
        self.assertRegex(header["status"].strip(), FINISHED)
        extra = find(events, half="Extra time")
        self.assertTrue(extra and all(int(e["minute"].split("'")[0].split("+")[0]) >= 91 for e in extra))
        self.assertTrue(find(events, half="Extra time", type="Yellow card", minute="120'"))
        self.assertEqual(find(events, half="Penalties"), [])
        self.assertEqual(sum(e["type"] in GOAL_TYPES for e in events), 6)

    def test_extra_time_penalty_goal(self):                    # Hallescher 2-5 Schalke (sau hiệp phụ)
        header, events = self.run_fixture("zwxW4x53")
        self.assertRegex(header["status"].strip(), FINISHED)
        pen = find(events, type="Penalty goal")
        self.assertEqual([(e["minute"], e["player"], e["detail"]) for e in pen], [("81'", "Dzeko E.", "")])
        self.assertEqual(sum(e["type"] in GOAL_TYPES for e in events), 7)

    def test_var_and_penalty_goal(self):                       # Malaga 1-3 Villarreal
        _, events = self.run_fixture("GGiPsLP1")
        var = find(events, type="VAR")
        self.assertEqual([(e["minute"], e["player"], e["detail"]) for e in var],
                         [("82'", "Romero C.", "Goal Disallowed - offside")])
        self.assertEqual([(e["minute"], e["player"], e["detail"]) for e in find(events, type="Penalty goal")],
                         [("86'", "Gueye P.", "")])

    def test_penalty_missed_is_not_a_card(self):               # Athletic Bilbao 0-0 Alaves
        _, events = self.run_fixture("nJYlbtAr")
        self.assertEqual([(e["minute"], e["side"], e["player"], e["detail"]) for e in find(events, type="Penalty missed")],
                         [("70'", "home", "Sancet O.", "")])
        self.assertEqual(find(events, type="Card"), [])

    def test_second_yellow(self):                              # Betis 1-0 Getafe
        _, events = self.run_fixture("l0jpbLho")
        self.assertEqual([(e["minute"], e["player"], e["detail"]) for e in find(events, type="Second yellow (→ red)")],
                         [("87'", "Martin M.", "Roughing")])
        self.assertEqual(find(events, type="Red card"), [])

    def test_own_goal(self):                                   # Fulham 1-1 Manchester Utd
        _, events = self.run_fixture("vq6T9aFr")
        self.assertEqual([(e["minute"], e["side"], e["player"]) for e in find(events, type="Own goal")],
                         [("63'", "home", "Martinez Li.")])

    def test_red_card_without_player_name(self):               # Xuan Thien Phu Tho 1-1 Khanh Hoa (V.League 2)
        _, events = self.run_fixture("r5x1FLmS")
        self.assertEqual([(e["minute"], e["side"], e["player"]) for e in find(events, type="Red card")],
                         [("52'", "home", "")])

    def test_no_unclassified_events_in_any_fixture(self):
        for mid in ("rJi7Md3T", "d8pxv90m", "zwxW4x53", "GGiPsLP1", "nJYlbtAr", "l0jpbLho", "vq6T9aFr", "r5x1FLmS", "vLuGlk0n"):
            with self.subTest(mid=mid):
                _, events = self.run_fixture(mid)
                self.assertEqual(find(events, type="Card"), [])
                self.assertTrue(all(e["side"] in ("home", "away") for e in events))


class FinishedStatusTest(unittest.TestCase):
    def test_finished_statuses(self):
        for status in ("Finished", "FINISHED", "After Extra Time", "AFTER 90 MINUTES", "After Penalties", "AET"):
            self.assertRegex(status, FINISHED)
        for status in ("", "1st Half", "Half Time", "2nd Half", "Postponed", "Cancelled", "Abandoned", "45+2'"):
            self.assertNotRegex(status, FINISHED)


if __name__ == "__main__":
    unittest.main()
