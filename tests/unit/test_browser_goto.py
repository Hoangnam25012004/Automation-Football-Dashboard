"""Ánh xạ lỗi điều hướng → mã lỗi (design doc §4.3, diễn tập lỗi ở bước 4.2) bằng page giả."""
import unittest

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from crawler import browser as fsb
from crawler.errors import CrawlError


class FakeResponse:
    def __init__(self, status):
        self.status = status


class FakePage:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def goto(self, url, wait_until=None):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class GotoTest(unittest.TestCase):
    def code(self, page):
        with self.assertRaises(CrawlError) as ctx:
            fsb.goto(page, "https://www.flashscore.com/")
        return ctx.exception.code

    def test_ok(self):
        page = FakePage(FakeResponse(200))
        self.assertEqual(fsb.goto(page, "https://www.flashscore.com/").status, 200)

    def test_retry_once_then_ok(self):
        page = FakePage(PlaywrightTimeout("slow"), FakeResponse(200))
        self.assertEqual(fsb.goto(page, "https://www.flashscore.com/").status, 200)
        self.assertEqual(page.calls, 2)

    def test_timeout_twice(self):
        self.assertEqual(self.code(FakePage(PlaywrightTimeout("slow"), PlaywrightTimeout("slow"))), "E_TIMEOUT")

    def test_offline(self):
        err = PlaywrightError("net::ERR_INTERNET_DISCONNECTED at https://www.flashscore.com/")
        self.assertEqual(self.code(FakePage(err, err)), "E_NETWORK")

    def test_blocked(self):
        self.assertEqual(self.code(FakePage(FakeResponse(403))), "E_BLOCKED")
        self.assertEqual(self.code(FakePage(FakeResponse(429))), "E_BLOCKED")

    def test_not_found_is_returned_to_caller(self):
        self.assertEqual(fsb.goto(FakePage(FakeResponse(404)), "https://www.flashscore.com/").status, 404)


class ParallelSettingTest(unittest.TestCase):
    def test_fs_parallel(self):
        import os
        from unittest import mock
        for value, expected in ((None, 3), ("1", 1), ("5", 5), ("0", 1), ("99", 7), ("abc", 3)):
            env = {} if value is None else {"FS_PARALLEL": value}
            with mock.patch.dict(os.environ, env, clear=False):
                if value is None:
                    os.environ.pop("FS_PARALLEL", None)
                self.assertEqual(fsb.parallel(), expected, value)


if __name__ == "__main__":
    unittest.main()
