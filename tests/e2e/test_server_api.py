"""API của server.py với runner giả (offline, tất định) — design doc §4, bước 2.2–2.4."""
import json
import threading
import time
import unittest

from crawler.errors import CrawlError
from tests import _support

URL = "https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/?mid=vLuGlk0n"


class FakeRunner:
    def __init__(self, behaviour: str = "ok"):
        self.behaviour = behaviour
        self.gate = threading.Event()
        self.gate.set()
        self.calls: list[str] = []

    def __call__(self, url, progress):
        self.calls.append(url)
        progress({"phase": "header", "done": 0, "total": 10, "message": "Opening match page…"})
        self.gate.wait(10)
        if self.behaviour == "not_finished":
            raise CrawlError("E_MATCH_NOT_FINISHED")
        if self.behaviour == "boom":
            raise RuntimeError("unexpected")
        progress({"phase": "done", "done": 10, "total": 10, "message": "Done"})
        return {"schemaVersion": 1, "stats": {"home": "AAA"}, "warnings": [{"code": "W_NO_MID", "message": "x"}]}


def wait_job(base: str, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, _, body = _support.http("GET", f"{base}/api/matches/{job_id}")
        job = json.loads(body)
        if job.get("status") in ("done", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError("job không kết thúc")


class ServerApiTest(unittest.TestCase):
    def test_static_whitelist(self):
        with _support.running_server(FakeRunner()) as base:
            for path in ("/", "/match_report.html"):
                status, headers, body = _support.http("GET", base + path)
                self.assertEqual(status, 200)
                self.assertTrue(headers["Content-Type"].startswith("text/html"))
                self.assertEqual(body, _support.HTML.read_bytes())
            for path in ("/server.py", "/flashscore_scraper.py", "/.git/config", "/../server.py", "/tests/"):
                self.assertEqual(_support.http("GET", base + path)[0], 404, path)

    def test_health_and_unknown_api(self):
        with _support.running_server(FakeRunner()) as base:
            status, _, body = _support.http("GET", base + "/api/health")
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(body)["ok"])
            status, _, body = _support.http("GET", base + "/api/nope")
            self.assertEqual((status, json.loads(body)["error"]["code"]), (404, "E_NOT_FOUND"))
            status, _, body = _support.http("GET", base + "/api/matches/unknownjob")
            self.assertEqual((status, json.loads(body)["error"]["code"]), (404, "E_JOB_NOT_FOUND"))

    def test_rejects_bad_requests(self):
        with _support.running_server(FakeRunner()) as base:
            # sai Content-Type (request "đơn giản" kiểu form/text không preflight) ⇒ 415
            status, _, _ = _support.http("POST", base + "/api/matches", json.dumps({"url": URL}).encode(),
                                         {"Content-Type": "text/plain"})
            self.assertEqual(status, 415)
            # Origin lạ ⇒ 403
            status, body = _support.post_json(base, {"url": URL}, {"Origin": "https://evil.example"})
            self.assertEqual((status, body["error"]["code"]), (403, "E_FORBIDDEN"))
            # Host lạ (DNS rebinding) ⇒ 403
            status, _, _ = _support.http("GET", base + "/", headers={"Host": "evil.example"})
            self.assertEqual(status, 403)
            # body quá lớn ⇒ 413
            status, _, _ = _support.http("POST", base + "/api/matches", b"{" + b" " * 4000 + b"}",
                                         {"Content-Type": "application/json"})
            self.assertEqual(status, 413)
            # JSON hỏng / thiếu url / url sai ⇒ 400 E_URL_INVALID
            for payload in (b"not json", b'{"x":1}', b'{"url":5}'):
                status, _, body = _support.http("POST", base + "/api/matches", payload, {"Content-Type": "application/json"})
                self.assertEqual((status, json.loads(body)["error"]["code"]), (400, "E_URL_INVALID"), payload)
            status, body = _support.post_json(base, {"url": "https://evil.example/match/football/a-AAAAAAAA/b-BBBBBBBB/"})
            self.assertEqual((status, body["error"]["code"]), (400, "E_URL_INVALID"))
            # Origin của chính server thì được nhận
            status, body = _support.post_json(base, {"url": URL}, {"Origin": base})
            self.assertEqual(status, 202)

    def test_job_lifecycle(self):
        runner = FakeRunner()
        with _support.running_server(runner) as base:
            status, body = _support.post_json(base, {"url": "  " + URL + "  "})
            self.assertEqual(status, 202)
            self.assertEqual(body["status"], "queued")
            job = wait_job(base, body["jobId"])
            self.assertEqual(job["status"], "done")
            self.assertEqual(job["progress"]["done"], 10)
            self.assertEqual(job["result"]["stats"]["home"], "AAA")
            self.assertEqual(job["warnings"][0]["code"], "W_NO_MID")
            self.assertEqual(runner.calls, [URL])                     # server đã trim link

    def test_busy_when_one_running_and_one_queued(self):
        runner = FakeRunner()
        runner.gate.clear()
        with _support.running_server(runner) as base:
            s1, j1 = _support.post_json(base, {"url": URL})
            s2, j2 = _support.post_json(base, {"url": URL})
            s3, j3 = _support.post_json(base, {"url": URL})
            self.assertEqual((s1, s2), (202, 202))
            self.assertEqual((s3, j3["error"]["code"]), (429, "E_BUSY"))
            runner.gate.set()
            self.assertEqual(wait_job(base, j1["jobId"])["status"], "done")
            self.assertEqual(wait_job(base, j2["jobId"])["status"], "done")
            self.assertEqual(_support.post_json(base, {"url": URL})[0], 202)     # hết bận ⇒ nhận job mới

    def test_crawl_error_is_reported(self):
        with _support.running_server(FakeRunner("not_finished")) as base:
            job = wait_job(base, _support.post_json(base, {"url": URL})[1]["jobId"])
            self.assertEqual(job["status"], "error")
            self.assertEqual(job["error"]["code"], "E_MATCH_NOT_FINISHED")
            self.assertTrue(job["error"]["message"])

    def test_unexpected_exception_does_not_kill_worker(self):
        runner = FakeRunner("boom")
        with _support.running_server(runner) as base:
            job = wait_job(base, _support.post_json(base, {"url": URL})[1]["jobId"])
            self.assertEqual(job["error"]["code"], "E_INTERNAL")
            runner.behaviour = "ok"
            job = wait_job(base, _support.post_json(base, {"url": URL})[1]["jobId"])
            self.assertEqual(job["status"], "done")


if __name__ == "__main__":
    unittest.main()
