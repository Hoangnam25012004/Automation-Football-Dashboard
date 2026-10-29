"""Smoke test thật: server.py + crawler thật trên trận tham chiếu #1 (cổng G2).

FS_LIVE=1 python -m unittest tests.live.test_live_server
"""
import json
import time
import unittest

from tests import _support

URL = "https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/?mid=vLuGlk0n"


@unittest.skipUnless(_support.LIVE, "đặt FS_LIVE=1 để chạy test chạm flashscore.com")
class LiveServerTest(unittest.TestCase):
    def test_post_poll_done(self):
        with _support.running_server() as base:
            status, body = _support.post_json(base, {"url": URL})
            self.assertEqual(status, 202)
            seen_steps = set()
            deadline = time.monotonic() + 180
            job = None
            while time.monotonic() < deadline:
                job = json.loads(_support.http("GET", f"{base}/api/matches/{body['jobId']}")[2])
                seen_steps.add(job["progress"]["done"])
                if job["status"] in ("done", "error"):
                    break
                time.sleep(1)
            self.assertEqual(job["status"], "done", job.get("error"))
            result = job["result"]
            self.assertEqual((result["stats"]["home"], result["stats"]["away"]), ("JOH", "SVA"))
            self.assertEqual(len(result["summary"]["events"]), 21)
            self.assertEqual(len(result["lineups"]["formation"]["players"]), 22)
            self.assertEqual(result["warnings"], [])
            self.assertFalse(result["teamStats"]["possessionReliable"])     # giải này: possession 50/50 giả
            self.assertEqual(result["meta"]["competition"], "ASEAN Club Championship")
            self.assertGreaterEqual(len(seen_steps), 3)            # tiến độ được cập nhật trong lúc chạy


if __name__ == "__main__":
    unittest.main()
