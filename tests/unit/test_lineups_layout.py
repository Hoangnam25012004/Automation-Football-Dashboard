"""Hình học sơ đồ + dựng lineups từ dữ liệu thô giả lập (design doc §5.3, §5.4)."""
import base64
import io
import unittest

from crawler.errors import Warnings
from crawler.lineups import LINEUP_KEYS, PLACEHOLDER_PNG, build_lineups, layout_formation, lineup_images


def player(pid, num, x):
    return {"id": pid, "num": num, "x": x, "y": 0.0}


class LayoutFormationTest(unittest.TestCase):
    def setUp(self):
        # nhà 4-2-3-1 (DOM GK → tiền đạo); khách 3-5-2 với thứ tự DOM phải → trái như Flashscore
        self.raw = {
            "label": ["4 - 2 - 3 - 1", "Formation", "3 - 5 - 2"],
            "home": [[player("h1", "1", 0.5)],
                     [player("h2", "2", 0.2), player("h3", "3", 0.4), player("h4", "4", 0.6), player("h5", "5", 0.8)],
                     [player("h6", "6", 0.35), player("h7", "7", 0.65)],
                     [player("h8", "8", 0.25), player("h9", "9", 0.5), player("h10", "10", 0.75)],
                     [player("h11", "11", 0.5)]],
            "away": [[player("a1", "1", 0.5)],
                     [player("a4", "4", 0.75), player("a3", "3", 0.5), player("a2", "2", 0.25)],
                     [player("a9", "9", 0.9), player("a8", "8", 0.7), player("a7", "7", 0.5), player("a6", "6", 0.3), player("a5", "5", 0.1)],
                     [player("a11", "11", 0.65), player("a10", "10", 0.35)]],
        }
        self.names = {f"h{i}": f"Home {i}" for i in range(1, 12)} | {f"a{i}": f"Away {i}" for i in range(1, 12)}

    def layout(self):
        return layout_formation(self.raw, lambda pid, fb: self.names.get(pid, fb))

    def test_shape_and_constants(self):
        fm = self.layout()
        self.assertEqual((fm["w"], fm["h"]), (100, 176))           # khớp viewBox của pitchSVG
        self.assertEqual(len(fm["players"]), 22)
        self.assertTrue(all(p["ok"] for p in fm["players"]))
        self.assertEqual(set(fm["players"][0]), {"num", "name", "ok", "side", "x", "y"})

    def test_home_rows_top_half_gk_first(self):
        home = [p for p in self.layout()["players"] if p["side"] == "home"]
        ys = sorted({p["y"] for p in home})
        self.assertEqual(ys, [0.1, 0.1825, 0.265, 0.3475, 0.43])
        gk = next(p for p in home if p["num"] == "1")
        self.assertEqual((gk["y"], gk["name"]), (0.1, "Home 1"))

    def test_away_rows_mirrored_forwards_on_top(self):
        away = [p for p in self.layout()["players"] if p["side"] == "away"]
        gk = next(p for p in away if p["num"] == "1")
        fwd = next(p for p in away if p["num"] == "10")
        self.assertEqual(gk["y"], 0.9)
        self.assertEqual(fwd["y"], 0.57)
        self.assertTrue(all(0.57 <= p["y"] <= 0.9 for p in away))

    def test_row_order_sorted_by_x(self):
        away = [p for p in self.layout()["players"] if p["side"] == "away" and p["y"] == round(0.57 + 0.33 * (2 / 3), 4)]
        self.assertEqual([p["num"] for p in away], ["2", "3", "4"])

    def test_too_few_players_is_none(self):
        self.assertIsNone(layout_formation({"home": [[player("h1", "1", 0.5)]], "away": []}, lambda pid, fb: fb))
        self.assertIsNone(layout_formation(None, lambda pid, fb: fb))

    def test_single_row_side_centered(self):
        fm = layout_formation({"home": [[player("h1", "1", 0.2), player("h2", "2", 0.4),
                                         player("h3", "3", 0.6), player("h4", "4", 0.8)]], "away": []},
                              lambda pid, fb: fb)
        self.assertEqual({p["y"] for p in fm["players"]}, {round(0.10 + 0.33 * 0.5, 4)})


class BuildLineupsTest(unittest.TestCase):
    def raw(self, heads=("substituted players", "starting lineups", "substitutes", "coaches")):
        gen = lambda pid, num, name: {"kind": "general", "id": pid, "num": num, "name": name, "role": None}
        starting = [[gen(f"h{i}", str(i), f"List H{i}") for i in range(1, 12)],
                    [gen(f"a{i}", str(i), f"List A{i}") for i in range(1, 12)]]
        bench = [[gen("h12", "12", "Bench H12"), gen("h13", "13", "Bench H13")], [gen("a12", "12", "Bench A12")]]
        changes = [[{"kind": "sub", "onId": "h12", "onName": "Bench H12", "rating": "7.0", "offId": "h9",
                     "offName": "Short H9", "minute": "67'"}],
                   [{"kind": "sub", "onId": "a12", "onName": "Bench A12", "rating": None, "offId": "a10",
                     "offName": "Short A10", "minute": "45+2'"}]]
        coaches = [[{"kind": "general", "id": None, "num": None, "name": "Coach H", "role": None}],
                   [{"kind": "general", "id": None, "num": None, "name": "Coach A", "role": None}]]
        return {"groups": [{"head": heads[0], "sides": changes}, {"head": heads[1], "sides": starting},
                           {"head": heads[2], "sides": bench}, {"head": heads[3], "sides": coaches}],
                "formation": None}

    def roster(self):
        return {f"h{i}": f"Stats H{i}" for i in range(1, 13)} | {f"a{i}": f"Stats A{i}" for i in range(1, 13)}

    def test_shapes_match_lineup_ocr(self):
        w = Warnings()
        lu = build_lineups(self.raw(), self.roster(), w)
        self.assertEqual(set(lu), set(LINEUP_KEYS))
        self.assertEqual(len(lu["starting_xi"]), 11)
        self.assertEqual(lu["starting_xi"][0], {"homeNum": "1", "awayNum": "1",
                                                "home": {"name": "Stats H1", "ok": True}, "away": {"name": "Stats A1", "ok": True}})
        # h13 không có trong roster stats (dự bị chưa ra sân) ⇒ dùng tên trong danh sách lineups
        self.assertEqual(lu["substitutes"][1], {"homeNum": "13", "awayNum": "",
                                                "home": {"name": "Bench H13", "ok": True}, "away": {"name": "", "ok": False}})
        self.assertEqual(lu["substituted"], {"home": [{"on": "Stats H12", "off": "Stats H9", "min": "67"}],
                                             "away": [{"on": "Stats A12", "off": "Stats A10", "min": "45+2"}]})
        self.assertEqual(lu["coaches"], {"home": {"name": "Coach H", "ok": True}, "away": {"name": "Coach A", "ok": True}})
        self.assertIsNone(lu["formation"])
        self.assertEqual(w.codes(), [])

    def test_names_prefer_stats_roster_then_list(self):
        lu = build_lineups(self.raw(), {}, Warnings())
        self.assertEqual(lu["starting_xi"][0]["home"]["name"], "List H1")
        self.assertEqual(lu["substituted"]["home"][0]["off"], "List H9")   # tên ra lấy theo id từ danh sách

    def test_unknown_headings_fall_back_to_structure(self):
        lu = build_lineups(self.raw(heads=("a", "b", "c", "d")), self.roster(), Warnings())
        self.assertEqual(len(lu["starting_xi"]), 11)
        self.assertEqual(len(lu["substituted"]["home"]), 1)
        self.assertEqual(lu["coaches"]["home"]["name"], "Coach H")
        self.assertEqual(len(lu["substitutes"]), 2)

    def test_roster_mismatch_and_partial_warnings(self):
        raw = self.raw()
        raw["groups"][1]["sides"][0].pop()               # đội nhà chỉ còn 10 người đá chính
        w = Warnings()
        build_lineups(raw, {"h1": "Stats H1"}, w)
        self.assertIn("W_LINEUPS_PARTIAL", w.codes())
        self.assertIn("W_ROSTER_MISMATCH", w.codes())


class LineupImagesTest(unittest.TestCase):
    def test_invariant_key_present_iff_data(self):
        lu = {"formation": None, "starting_xi": [1], "substituted": None, "substitutes": [1], "coaches": {"home": {}}}
        self.assertEqual(set(lineup_images(lu)), {"starting_xi", "substitutes", "coaches"})
        self.assertEqual(lineup_images(None), {})

    def test_placeholder_is_a_real_1x1_png(self):
        from PIL import Image
        head, data = PLACEHOLDER_PNG.split(",", 1)
        self.assertEqual(head, "data:image/png;base64")
        img = Image.open(io.BytesIO(base64.b64decode(data)))
        self.assertEqual((img.format, img.size), ("PNG", (1, 1)))


if __name__ == "__main__":
    unittest.main()
