"""Ghép kết quả + kiểm tra chéo (design doc §5.1, §6.7)."""
import unittest

from crawler.assemble import _num, assemble
from crawler.errors import Warnings
from crawler.header import MatchInfo
from crawler.player_stats import TABS, StatsResult
from crawler.urls import parse_match_url

REF = parse_match_url("https://www.flashscore.com/match/football/home-AAAAAAAA/away-BBBBBBBB/?mid=CCCCCCCC")


def stats_with(home_goals, away_goals, home_og="-", away_og="-") -> StatsResult:
    def team(goals, og):
        teams = {label: {"headers": [], "rows": []} for _, label in TABS}
        teams["General"] = {"headers": ["Player", "Position", "Goals", "Own goals"],
                            "rows": [{"Player": "P1", "Position": "-", "Goals": goals, "Own goals": og}]}
        return teams
    return StatsResult(home="HOM", away="AWA", teams={"HOM": team(home_goals, home_og), "AWA": team(away_goals, away_og)})


def info(h, a) -> MatchInfo:
    return MatchInfo("Home FC", "Away FC", "01.01.2026 12:00", h, a, "FINISHED", "", "")


def goal(side):
    return {"minute": "10'", "half": "1st half", "side": side, "team": "", "type": "Goal", "player": "P",
            "detail": "", "score": "1 - 0"}


class NumTest(unittest.TestCase):
    def test_same_semantics_as_web_U_num(self):
        self.assertEqual(_num("-"), 0)
        self.assertEqual(_num(""), 0)
        self.assertEqual(_num(None), 0)
        self.assertEqual(_num("3"), 3)
        self.assertEqual(_num("0.60"), 0.6)
        self.assertEqual(_num("-1.74"), -1.74)
        self.assertEqual(_num("23/30 (77%)"), 23)
        self.assertEqual(_num("1/2"), 1)


class AssembleTest(unittest.TestCase):
    def test_contract_shape(self):
        w = Warnings()
        r = assemble(REF, info(1, 0), stats_with("1", "-"), [goal("home")], 1, ("data:image/png;base64,AA", None), None, w)
        self.assertEqual(list(r), ["schemaVersion", "matchId", "sourceUrl", "fetchedAt", "stats", "summary",
                                   "lineups", "lineupImages", "warnings"])
        self.assertEqual(r["stats"]["matchTitle"], "Home FC  vs  Away FC")
        self.assertEqual(r["stats"]["matchDate"], "")
        self.assertEqual((r["stats"]["home"], r["stats"]["away"]), ("HOM", "AWA"))
        self.assertEqual(r["summary"]["finalScore"], {"h": 1, "a": 0})
        self.assertEqual(r["lineups"], None)
        self.assertEqual(r["lineupImages"], {})
        self.assertEqual(r["matchId"], "CCCCCCCC")
        self.assertEqual(w.codes(), [])

    def test_own_goal_counts_for_the_opponent(self):
        w = Warnings()
        assemble(REF, info(2, 0), stats_with("1", "-", away_og="1"), [goal("home"), goal("home")], 2, (None, None), None, w)
        self.assertEqual(w.codes(), [])

    def test_score_mismatch_warning(self):
        w = Warnings()
        assemble(REF, info(2, 0), stats_with("1", "-"), [goal("home"), goal("home")], 2, (None, None), None, w)
        self.assertEqual(w.codes(), ["W_SCORE_MISMATCH"])

    def test_timeline_warnings(self):
        w = Warnings()
        assemble(REF, info(2, 1), stats_with("2", "1"), [goal("home")], 3, (None, None), None, w)
        self.assertEqual(w.codes(), ["W_TIMELINE_SCORE_MISMATCH"])
        w = Warnings()
        r = assemble(REF, info(2, 1), stats_with("2", "1"), [], 0, (None, None), None, w)
        self.assertEqual(w.codes(), ["W_TIMELINE_EMPTY"])
        self.assertIsNone(r["summary"])                  # không sự kiện, không logo ⇒ như luồng cũ khi thiếu file summary

    def test_goalless_draw_without_events_is_fine(self):
        w = Warnings()
        assemble(REF, info(0, 0), stats_with("-", "-"), [], 0, (None, None), None, w)
        self.assertEqual(w.codes(), [])


class WarningsTest(unittest.TestCase):
    def test_dedup_and_detail_merge(self):
        w = Warnings()
        w.add("W_STATS_TAB_EMPTY", "Shots")
        w.add("W_STATS_TAB_EMPTY", "Attack")
        w.add("W_STATS_TAB_EMPTY", "Shots")
        self.assertEqual(len(w.items), 1)
        self.assertEqual(w.items[0]["detail"], "Shots; Attack")


if __name__ == "__main__":
    unittest.main()
