"""Bấm có thử lại khi chọn đội ở player stats (lỗi chập chờn đã gặp trên Hugging Face)."""
import unittest

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from crawler import player_stats


class FakeKeyboard:
    def __init__(self):
        self.pressed = []

    def press(self, key):
        self.pressed.append(key)


class FakePage:
    def __init__(self):
        self.keyboard = FakeKeyboard()
        self.waits = []

    def wait_for_timeout(self, ms):
        self.waits.append(ms)


class FakeLocator:
    def __init__(self, fail_times):
        self.fail_times, self.clicks = fail_times, []

    def wait_for(self, state, timeout):
        pass

    def scroll_into_view_if_needed(self, timeout):
        pass

    def click(self, timeout, force):
        self.clicks.append(force)
        if len(self.clicks) <= self.fail_times:
            raise PlaywrightTimeout("Locator.click: Timeout 5000ms exceeded.")


class ClickRetryTest(unittest.TestCase):
    def test_first_try_unchanged(self):
        page, loc = FakePage(), FakeLocator(0)
        player_stats._click_retrying(page, loc)
        self.assertEqual(loc.clicks, [False])
        self.assertEqual(page.keyboard.pressed, [])

    def test_recovers_after_transient_timeouts_and_forces_last(self):
        page, loc = FakePage(), FakeLocator(2)
        player_stats._click_retrying(page, loc)
        self.assertEqual(loc.clicks, [False, False, True])
        self.assertEqual(page.keyboard.pressed, ["Escape", "Escape"])

    def test_gives_up_after_three(self):
        page, loc = FakePage(), FakeLocator(5)
        with self.assertRaises(PlaywrightTimeout):
            player_stats._click_retrying(page, loc)
        self.assertEqual(len(loc.clicks), 3)

    def test_after_condition_failure_is_retried(self):
        page, loc = FakePage(), FakeLocator(0)
        calls = []

        def after():
            calls.append(1)
            if len(calls) == 1:
                raise PlaywrightTimeout("options not visible")
        player_stats._click_retrying(page, loc, after=after)
        self.assertEqual((len(loc.clicks), len(calls)), (2, 2))


if __name__ == "__main__":
    unittest.main()
