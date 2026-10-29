"""API bản cloud (design doc cloud §7–§10, §14): tài khoản, quyền, CSRF, job + thư viện, hạn mức,
ngắt mạch, chia sẻ, header bảo mật. Server thật (Uvicorn) + nguồn dữ liệu giả — không chạm flashscore.com.
"""
import unittest

from tests.cloud._harness import CLOUD_DEPS, LINKS, PASSWORD, Client, CloudServer, last_link_token


@unittest.skipUnless(CLOUD_DEPS, "cần pip install -r requirements-cloud.txt")
class AccountTest(unittest.TestCase):
    def test_register_verify_approve_login(self):
        with CloudServer() as srv:
            admin = srv.admin()
            c = Client(srv.base)
            status, body, _ = c.post("/api/auth/register", {"email": "coach@example.com", "password": PASSWORD})
            self.assertEqual((status, body), (200, {"ok": True}))
            self.assertEqual(c.login("coach@example.com")[1]["error"]["code"], "E_ACCOUNT_UNVERIFIED")
            status, body, _ = c.post("/api/auth/verify", {"token": last_link_token("coach@example.com", "verify")})
            self.assertEqual(body["status"], "pending")                          # REGISTRATION=approval
            self.assertEqual(c.login("coach@example.com")[1]["error"]["code"], "E_ACCOUNT_PENDING")
            users = admin.get("/api/admin/users")[1]["users"]
            uid = next(u["id"] for u in users if u["email"] == "coach@example.com")
            status, body, _ = admin.post(f"/api/admin/users/{uid}", {"status": "active"})
            self.assertEqual((status, body["status"]), (200, "active"))
            status, body, headers = c.login("coach@example.com")
            self.assertEqual(status, 200)
            self.assertEqual(body["user"]["email"], "coach@example.com")
            cookie = headers.get("set-cookie", "") + "|" + "|".join(v for k, v in headers.items() if k.lower() == "set-cookie")
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=lax", cookie.replace("SameSite=Lax", "SameSite=lax"))
            status, me, _ = c.get("/api/me")
            self.assertEqual((status, me["user"]["role"], me["quota"]["limit"]), (200, "member", 10))
            # token xác minh chỉ dùng được 1 lần
            self.assertEqual(c.post("/api/auth/verify", {"token": last_link_token("coach@example.com", "verify")})[0], 400)

    def test_open_registration_and_invite_only(self):
        with CloudServer(registration="open") as srv:
            c = Client(srv.base)
            c.post("/api/auth/register", {"email": "a@example.com", "password": PASSWORD})
            _, body, _ = c.post("/api/auth/verify", {"token": last_link_token("a@example.com", "verify")})
            self.assertEqual(body["status"], "active")
            self.assertEqual(c.login("a@example.com")[0], 200)
            admin = srv.admin()
            admin.post("/api/admin/settings", {"registration": "invite"})
            status, body, _ = Client(srv.base).post("/api/auth/register", {"email": "b@example.com", "password": PASSWORD})
            self.assertEqual((status, body["error"]["code"]), (403, "E_REGISTRATION_CLOSED"))
            # mời: tài khoản active + link đặt mật khẩu
            status, body, _ = admin.post("/api/admin/users", {"email": "inv@example.com"})
            self.assertEqual((status, body["status"]), (200, "active"))
            inv = Client(srv.base)
            self.assertEqual(inv.post("/api/auth/reset", {"token": last_link_token("inv@example.com", "reset"),
                                                          "password": PASSWORD})[0], 200)
            self.assertEqual(inv.login("inv@example.com")[0], 200)

    def test_register_does_not_reveal_existing_email(self):
        with CloudServer() as srv:
            srv.admin("owner@example.com")
            status, body, _ = Client(srv.base).post("/api/auth/register", {"email": "owner@example.com", "password": PASSWORD})
            self.assertEqual((status, body), (200, {"ok": True}))
            from cloud import mail
            self.assertIn("sign-up attempt", mail.OUTBOX[-1]["subject"])

    def test_weak_password_and_bad_email(self):
        with CloudServer() as srv:
            c = Client(srv.base)
            self.assertEqual(c.post("/api/auth/register", {"email": "x@example.com", "password": "short"})[1]["error"]["code"], "E_WEAK_PASSWORD")
            self.assertEqual(c.post("/api/auth/register", {"email": "x@example.com", "password": "password123"})[1]["error"]["code"], "E_WEAK_PASSWORD")
            self.assertEqual(c.post("/api/auth/register", {"email": "not-an-email", "password": PASSWORD})[0], 400)

    def test_login_errors_are_generic_and_rate_limited(self):
        with CloudServer() as srv:
            srv.admin("boss@example.com")
            c = Client(srv.base)
            unknown = c.login("nobody@example.com")[1]["error"]
            wrong = c.login("boss@example.com", "wrong-password-123")[1]["error"]
            self.assertEqual(unknown, wrong)                                     # không lộ email nào tồn tại
            for _ in range(4):                                                   # 5 lần sai cho cùng email + IP
                c.login("boss@example.com", "wrong-password-123")
            status, body, _ = c.login("boss@example.com")                        # đúng mật khẩu nhưng đã quá 5 lần
            self.assertEqual((status, body["error"]["code"]), (429, "E_RATE_LIMITED"))

    def test_forgot_and_reset_password(self):
        with CloudServer() as srv:
            srv.member("m@example.com")
            c = Client(srv.base)
            self.assertEqual(c.post("/api/auth/forgot", {"email": "m@example.com"})[1], {"ok": True})
            self.assertEqual(c.post("/api/auth/forgot", {"email": "ghost@example.com"})[1], {"ok": True})
            token = last_link_token("m@example.com", "reset")
            self.assertEqual(c.post("/api/auth/reset", {"token": token, "password": "a-brand-new-pass"})[0], 200)
            self.assertEqual(c.post("/api/auth/reset", {"token": token, "password": "another-new-pass"})[0], 400)
            self.assertEqual(c.login("m@example.com")[0], 401)
            self.assertEqual(c.login("m@example.com", "a-brand-new-pass")[0], 200)

    def test_logout_and_delete_account(self):
        with CloudServer() as srv:
            admin = srv.admin()
            m = srv.member("bye@example.com")
            self.assertEqual(m.delete("/api/me", {"password": "wrong-password-1"})[0], 401)
            self.assertEqual(m.delete("/api/me", {"password": PASSWORD})[0], 200)
            self.assertEqual(Client(srv.base).login("bye@example.com")[0], 401)
            self.assertEqual(admin.delete("/api/me", {"password": PASSWORD})[1]["error"]["code"], "E_FORBIDDEN")  # admin cuối cùng
            self.assertEqual(admin.post("/api/auth/logout")[0], 200)
            self.assertEqual(admin.get("/api/me")[0], 401)

    def test_admin_cannot_lock_themselves_out(self):
        with CloudServer() as srv:
            admin = srv.admin()
            me = admin.get("/api/me")[1]["user"]["id"]
            self.assertEqual(admin.post(f"/api/admin/users/{me}", {"status": "disabled"})[0], 403)
            self.assertEqual(admin.post(f"/api/admin/users/{me}", {"role": "member"})[0], 403)

    def test_disabling_a_user_ends_their_sessions(self):
        with CloudServer() as srv:
            admin = srv.admin()
            m = srv.member("m@example.com")
            uid = m.get("/api/me")[1]["user"]["id"]
            admin.post(f"/api/admin/users/{uid}", {"status": "disabled"})
            self.assertEqual(m.get("/api/me")[0], 401)
            self.assertEqual(m.login("m@example.com")[1]["error"]["code"], "E_ACCOUNT_DISABLED")


@unittest.skipUnless(CLOUD_DEPS, "cần pip install -r requirements-cloud.txt")
class AccessControlTest(unittest.TestCase):
    def test_anonymous_is_rejected(self):
        with CloudServer() as srv:
            c = Client(srv.base)
            for method, path in (("GET", "/api/me"), ("GET", "/api/library"), ("GET", "/api/library/vLuGlk0n"),
                                 ("GET", "/api/matches/0123456789abcdef"), ("POST", "/api/matches"), ("GET", "/api/admin/users")):
                with self.subTest(path=path):
                    status, body, _ = c.request(method, path, {} if method == "POST" else None)
                    self.assertEqual((status, body["error"]["code"]), (401, "E_AUTH_REQUIRED"))

    def test_member_is_not_admin(self):
        with CloudServer() as srv:
            m = srv.member("m@example.com")
            for method, path in (("GET", "/api/admin/users"), ("GET", "/api/admin/settings"), ("GET", "/api/admin/audit"),
                                 ("POST", "/api/admin/settings"), ("POST", "/api/admin/users/1")):
                with self.subTest(path=path):
                    self.assertEqual(m.request(method, path, {"status": "active"} if method == "POST" else None)[0], 403)

    def test_csrf_and_origin(self):
        with CloudServer() as srv:
            m = srv.member("m@example.com")
            m.csrf_override = ""
            self.assertEqual(m.post("/api/matches", {"url": LINKS["vLuGlk0n"]})[1]["error"]["code"], "E_CSRF")
            m.csrf_override = "forged-token-value-123456"
            self.assertEqual(m.post("/api/matches", {"url": LINKS["vLuGlk0n"]})[1]["error"]["code"], "E_CSRF")
            m.csrf_override = None
            evil = Client(srv.base, origin="https://evil.example")
            evil.jar = m.jar
            evil.opener = m.opener
            self.assertEqual(evil.post("/api/matches", {"url": LINKS["vLuGlk0n"]})[0], 403)
            self.assertEqual(Client(srv.base, origin="https://evil.example").login("m@example.com")[0], 403)
            self.assertEqual(m.post("/api/matches", {"url": LINKS["vLuGlk0n"]})[0], 202)

    def test_security_headers_and_limits(self):
        with CloudServer() as srv:
            c = Client(srv.base)
            for path in ("/", "/report", "/m/vLuGlk0n", "/api/config"):
                with self.subTest(path=path):
                    status, _, headers = c.get(path)
                    self.assertEqual(status, 200)
                    lower = {k.lower(): v for k, v in headers.items()}
                    self.assertIn("frame-ancestors 'none'", lower["content-security-policy"])
                    self.assertEqual(lower["x-frame-options"], "DENY")
                    self.assertEqual(lower["x-content-type-options"], "nosniff")
            report_csp = {k.lower(): v for k, v in c.get("/report")[2].items()}["content-security-policy"]
            index_csp = {k.lower(): v for k, v in c.get("/")[2].items()}["content-security-policy"]
            self.assertIn("'unsafe-eval'", report_csp)          # chỉ trang báo cáo (Tesseract của demo)
            self.assertNotIn("'unsafe-eval'", index_csp)
            status, body, _ = c.post("/api/auth/login", {"email": "x" * 70000, "password": "y"})
            self.assertEqual((status, body["error"]["code"]), (413, "E_PAYLOAD_TOO_LARGE"))
            self.assertEqual(c.get("/m/..%2Fsecrets")[0], 404)
            self.assertEqual(c.get("/api/does-not-exist")[1]["error"]["code"], "E_NOT_FOUND")


@unittest.skipUnless(CLOUD_DEPS, "cần pip install -r requirements-cloud.txt")
class JobsAndLibraryTest(unittest.TestCase):
    def test_crawl_then_serve_from_library(self):
        with CloudServer() as srv:
            m = srv.member("m@example.com")
            status, job, _ = m.post("/api/matches", {"url": LINKS["vLuGlk0n"]})
            self.assertEqual((status, job["status"], job["mid"], job["position"]), (202, "queued", "vLuGlk0n", 1))
            # job cũ (shape giống server.py) trong lúc chờ
            _, polled, _ = m.get(f"/api/matches/{job['jobId']}")
            self.assertEqual((polled["status"], polled["progress"]["phase"]), ("queued", "queued"))
            self.assertEqual(srv.run_jobs(), 1)
            _, done, _ = m.get(f"/api/matches/{job['jobId']}")
            self.assertEqual(done["status"], "done")
            self.assertEqual(done["result"]["stats"]["home"], "JOH")
            self.assertEqual(done["result"]["schemaVersion"], 2)
            # lần 2: phục vụ ngay từ thư viện, không crawl, không tốn hạn mức
            other = srv.member("o@example.com")
            status, again, _ = other.post("/api/matches", {"url": LINKS["vLuGlk0n"]})
            self.assertEqual((status, again["status"]), (202, "done"))
            self.assertEqual(other.get(f"/api/matches/{again['jobId']}")[1]["result"]["stats"]["away"], "SVA")
            self.assertEqual(srv.source.calls, ["vLuGlk0n"])
            self.assertEqual(other.get("/api/me")[1]["quota"]["used"], 0)
            lib = other.get("/api/library")[1]
            self.assertEqual((lib["total"], lib["items"][0]["home"], lib["items"][0]["score"]), (1, "Johor DT", "6–0"))
            self.assertEqual(lib["items"][0]["competition"], "ASEAN Club Championship")
            self.assertEqual(other.get("/api/library?q=svay")[1]["total"], 1)
            self.assertEqual(other.get("/api/library?q=%25")[1]["total"], 0)       # ký tự LIKE được escape
            result = other.get("/api/library/vLuGlk0n")[1]
            self.assertEqual(result["result"]["matchId"], "vLuGlk0n")

    def test_duplicate_requests_share_one_job(self):
        with CloudServer() as srv:
            a, b = srv.member("a@example.com"), srv.member("b@example.com")
            ja = a.post("/api/matches", {"url": LINKS["GGiPsLP1"]})[1]
            jb = b.post("/api/matches", {"url": LINKS["GGiPsLP1"]})[1]
            self.assertEqual(ja["jobId"], jb["jobId"])
            self.assertEqual(b.get("/api/me")[1]["quota"]["used"], 0)
            srv.run_jobs()
            self.assertEqual(srv.source.calls, ["GGiPsLP1"])

    def test_link_validation(self):
        with CloudServer() as srv:
            m = srv.member("m@example.com")
            self.assertEqual(m.post("/api/matches", {"url": "https://evil.example/match/football/a/b/?mid=abcdefgh"})[1]["error"]["code"], "E_URL_INVALID")
            no_mid = LINKS["vLuGlk0n"].split("?")[0]
            self.assertEqual(m.post("/api/matches", {"url": no_mid})[1]["error"]["code"], "E_MID_REQUIRED")
            self.assertEqual(m.post("/api/matches", {"url": 42})[0], 400)

    def test_quotas(self):
        with CloudServer(quota_global_hourly=3) as srv:
            m = srv.member("m@example.com", quota=1)
            self.assertEqual(m.post("/api/matches", {"url": LINKS["vLuGlk0n"]})[0], 202)
            status, body, _ = m.post("/api/matches", {"url": LINKS["GGiPsLP1"]})
            self.assertEqual((status, body["error"]["code"]), (429, "E_QUOTA"))
            srv.run_jobs()
            self.assertEqual(m.post("/api/matches", {"url": LINKS["vLuGlk0n"]})[1]["status"], "done")   # thư viện: không tính
            admin = srv.admin()
            admin.post("/api/matches", {"url": LINKS["GGiPsLP1"]})
            admin.post("/api/matches", {"url": LINKS["d8pxv90m"]})
            status, body, _ = admin.post("/api/matches", {"url": LINKS["tW4rOkzg"]})      # trần toàn hệ thống 3/giờ
            self.assertEqual((status, body["error"]["code"]), (429, "E_SYSTEM_BUSY"))

    def test_crawl_error_is_reported_and_breaker_pauses_crawling(self):
        with CloudServer() as srv:
            m = srv.member("m@example.com", quota=50)
            m.post("/api/matches", {"url": LINKS["vLuGlk0n"]})
            srv.run_jobs()                                                            # thư viện có 1 trận
            srv.source.fail = ["E_MATCH_NOT_FINISHED"]
            job = m.post("/api/matches", {"url": LINKS["GGiPsLP1"]})[1]
            srv.run_jobs()
            err = m.get(f"/api/matches/{job['jobId']}")[1]
            self.assertEqual((err["status"], err["error"]["code"]), ("error", "E_MATCH_NOT_FINISHED"))
            srv.source.fail = ["E_BLOCKED", "E_BLOCKED"]
            m.post("/api/matches", {"url": LINKS["GGiPsLP1"]})
            m.post("/api/matches", {"url": LINKS["d8pxv90m"]})
            srv.run_jobs()
            status, body, _ = m.post("/api/matches", {"url": LINKS["tW4rOkzg"]})
            self.assertEqual((status, body["error"]["code"]), (503, "E_SOURCE_PAUSED"))
            self.assertEqual(m.get("/api/library/vLuGlk0n")[0], 200)                  # thư viện vẫn mở được
            self.assertTrue(m.get("/api/me")[1]["sourcePaused"])
            admin = srv.admin()
            self.assertFalse(admin.post("/api/admin/settings", {"resetBreaker": True})[1]["sourcePaused"])
            self.assertEqual(m.post("/api/matches", {"url": LINKS["tW4rOkzg"]})[0], 202)

    def test_share_link_and_ownership(self):
        with CloudServer() as srv:
            owner, other = srv.member("owner@example.com"), srv.member("other@example.com")
            owner.post("/api/matches", {"url": LINKS["vLuGlk0n"]})
            srv.run_jobs()
            self.assertEqual(other.post("/api/library/vLuGlk0n/share", {"enabled": True})[0], 403)      # IDOR
            self.assertEqual(other.post("/api/library/vLuGlk0n/refresh")[0], 403)
            token = owner.post("/api/library/vLuGlk0n/share", {"enabled": True})[1]["shareToken"]
            self.assertTrue(token)
            anon = Client(srv.base)
            status, body, _ = anon.get(f"/api/library/vLuGlk0n?s={token}")
            self.assertEqual((status, body["shared"], body["result"]["stats"]["home"]), (200, True, "JOH"))
            self.assertIsNone(body["entry"]["shareToken"])                          # người xem không thấy token
            self.assertEqual(anon.get("/api/library/vLuGlk0n?s=wrong-token-value")[0], 401)
            self.assertEqual(anon.get("/api/library/GGiPsLP1?s=" + token)[0], 401)  # token chỉ mở đúng trận đó
            self.assertIsNone(other.get("/api/library")[1]["items"][0]["shareToken"])
            owner.post("/api/library/vLuGlk0n/share", {"enabled": False})
            self.assertEqual(anon.get(f"/api/library/vLuGlk0n?s={token}")[0], 401)

    def test_refresh_cooldown(self):
        with CloudServer() as srv:
            owner = srv.member("owner@example.com")
            owner.post("/api/matches", {"url": LINKS["vLuGlk0n"]})
            srv.run_jobs()
            self.assertEqual(owner.post("/api/library/vLuGlk0n/refresh")[1]["error"]["code"], "E_REFRESH_TOO_SOON")
            admin = srv.admin()
            job = admin.post("/api/library/vLuGlk0n/refresh")[1]
            self.assertEqual(job["status"], "queued")
            srv.run_jobs()
            self.assertEqual(srv.source.calls, ["vLuGlk0n", "vLuGlk0n"])

    def test_stale_running_job_is_requeued(self):
        with CloudServer() as srv:
            m = srv.member("m@example.com")
            job = m.post("/api/matches", {"url": LINKS["vLuGlk0n"]})[1]
            conn = srv.conn()
            conn.execute("UPDATE jobs SET status = 'running', attempts = 1, started_ts = 0 WHERE id = ?", (job["jobId"],))
            conn.close()
            self.assertEqual(srv.run_jobs(), 1)
            self.assertEqual(m.get(f"/api/matches/{job['jobId']}")[1]["status"], "done")

    def test_health_reports_worker(self):
        with CloudServer() as srv:
            c = Client(srv.base)
            status, body, _ = c.get("/api/health")
            self.assertEqual((status, body["ok"]), (503, False))
            srv.beat()
            status, body, _ = c.get("/api/health")
            self.assertEqual((status, body["ok"], body["queue"]), (200, True, {"queued": 0, "running": 0}))


@unittest.skipUnless(CLOUD_DEPS, "cần pip install -r requirements-cloud.txt")
class BackupTest(unittest.TestCase):
    def test_backup_and_restore_roundtrip(self):
        from cloud import backup
        with CloudServer() as srv:
            m = srv.member("m@example.com")
            m.post("/api/matches", {"url": LINKS["vLuGlk0n"]})
            srv.run_jobs()
            archive = backup.make_backup(srv.settings)
            self.assertTrue(archive.name.endswith(".db.gz"))
            # khôi phục vào một đường dẫn khác (server đang chạy vẫn giữ file DB — runbook: dừng web + worker trước)
            import copy
            from cloud.db import connect
            target = copy.copy(srv.settings)
            target.db_path = srv.settings.db_path.with_name("restored.db")
            backup.restore(target, archive)
            conn = connect(target.db_path)
            try:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
