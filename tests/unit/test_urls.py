"""Bảng test tối thiểu cho crawler.urls (design doc §6.1)."""
import unittest

from crawler.errors import CrawlError
from crawler.urls import parse_match_url

USER_URL = "https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/?mid=vLuGlk0n"


class ParseMatchUrlTest(unittest.TestCase):
    def test_user_link(self):
        ref = parse_match_url(USER_URL)
        self.assertEqual((ref.team1, ref.team2, ref.mid), ("johor-dt-AVV6BGlb", "svay-rieng-IHTx6E4O", "vLuGlk0n"))
        self.assertEqual(ref.url(), USER_URL)
        self.assertEqual(ref.url("summary/lineups"),
                         "https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/summary/lineups/?mid=vLuGlk0n")
        self.assertEqual(ref.url("/summary/player-stats/top/"),
                         "https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/summary/player-stats/top/?mid=vLuGlk0n")

    def test_without_mid_is_accepted(self):
        ref = parse_match_url("https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/")
        self.assertIsNone(ref.mid)
        self.assertEqual(ref.url("summary"), "https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/summary/")

    def test_sub_page_fragment_whitespace_and_bare_host(self):
        for raw in [
            "https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/summary/lineups/?mid=vLuGlk0n",
            "https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/?mid=vLuGlk0n#/match-summary",
            "  " + USER_URL + "\n",
            "https://flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/?mid=vLuGlk0n",
            "https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O?mid=vLuGlk0n",
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(parse_match_url(raw).url(), USER_URL)

    def test_rejected(self):
        for raw in [
            "", "   ", "not a url",
            "http://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/?mid=vLuGlk0n",
            "https://www.flashscore.com.evil.example/match/football/a-AAAAAAAA/b-BBBBBBBB/",
            "https://evil.example/match/football/a-AAAAAAAA/b-BBBBBBBB/",
            "https://www.flashscore.com/match/tennis/a-AAAAAAAA/b-BBBBBBBB/",
            "https://www.flashscore.com/match/vLuGlk0n/#/match-summary",
            "https://www.flashscore.com/football/england/premier-league/",
            "https://user:pw@www.flashscore.com/match/football/a-AAAAAAAA/b-BBBBBBBB/",
            "https://www.flashscore.com:8443/match/football/a-AAAAAAAA/b-BBBBBBBB/",
            "https://www.flashscore.com/match/football/a-AAAAAAAA/b-BBBBBBBB/?mid=bad!mid",
            "https://www.flashscore.com/match/football/a%2FAAAAAAAA/b-BBBBBBBB/",
            "https://www.flashscore.com/match/football/johor dt/svay-rieng-IHTx6E4O/",
        ]:
            with self.subTest(raw=raw):
                with self.assertRaises(CrawlError) as ctx:
                    parse_match_url(raw)
                self.assertEqual(ctx.exception.code, "E_URL_INVALID")
                self.assertEqual(ctx.exception.status, 400)


if __name__ == "__main__":
    unittest.main()
