"""Unit offline của bản cloud: mật khẩu/token, migration + ràng buộc schema, DataSource Flashscore."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tests.cloud._harness import CLOUD_DEPS


@unittest.skipUnless(CLOUD_DEPS, "cần pip install -r requirements-cloud.txt")
class SecurityTest(unittest.TestCase):
    def test_password_hash_roundtrip_and_salt(self):
        from cloud.security import hash_password, verify_password
        d1, s1 = hash_password("correct-horse-battery")
        d2, s2 = hash_password("correct-horse-battery")
        self.assertNotEqual((d1, s1), (d2, s2))                      # salt ngẫu nhiên
        self.assertTrue(verify_password("correct-horse-battery", d1, s1))
        self.assertFalse(verify_password("correct-horse-batterY", d1, s1))

    def test_password_policy(self):
        from cloud.security import password_problem
        self.assertIsNotNone(password_problem("short"))
        self.assertIsNotNone(password_problem("password123"))
        self.assertIsNotNone(password_problem("aaaaaaaaaaaa"))
        self.assertIsNotNone(password_problem("coach-anna-2026", "coach-anna@example.com"))
        self.assertIsNone(password_problem("correct-horse-battery", "coach@example.com"))

    def test_tokens(self):
        from cloud.security import new_token, same, token_hash
        a, b = new_token(), new_token()
        self.assertNotEqual(a, b)
        self.assertGreaterEqual(len(a), 40)
        self.assertEqual(len(token_hash(a)), 64)
        self.assertTrue(same(a, a))
        self.assertFalse(same(a, b))


@unittest.skipUnless(CLOUD_DEPS, "cần pip install -r requirements-cloud.txt")
class SchemaTest(unittest.TestCase):
    def setUp(self):
        from cloud.db import connect, migrate
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / "t.db")
        self.applied = migrate(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_migrations_are_idempotent(self):
        from cloud.db import migrate
        self.assertEqual(self.applied, ["001_init"])
        self.assertEqual(migrate(self.conn), [])

    def test_constraints_live_in_the_schema(self):
        c = self.conn
        c.execute("INSERT INTO users(email, pw_hash, pw_salt, created_at) VALUES ('A@x.io', x'00', x'00', 'now')")
        with self.assertRaises(sqlite3.IntegrityError):              # email không phân biệt hoa thường
            c.execute("INSERT INTO users(email, pw_hash, pw_salt, created_at) VALUES ('a@X.io', x'00', x'00', 'now')")
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute("INSERT INTO users(email, pw_hash, pw_salt, role, created_at) VALUES ('b@x.io', x'00', x'00', 'root', 'now')")
        job = "INSERT INTO jobs(id, source, match_key, url, status, created_at, created_ts) VALUES (?, 'fs', 'm1', 'u', ?, 'now', 0)"
        c.execute(job, ("j1", "queued"))
        with self.assertRaises(sqlite3.IntegrityError):              # 1 job đang chờ/chạy cho mỗi trận
            c.execute(job, ("j2", "running"))
        c.execute(job, ("j3", "done"))                                # job đã xong thì không giới hạn
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute("INSERT INTO sessions(id, user_id, csrf, created_at, expires_at) VALUES ('s', 999, 'c', 'now', 'later')")

    def test_deleting_a_user_cascades_sessions_and_keeps_matches(self):
        c = self.conn
        uid = c.execute("INSERT INTO users(email, pw_hash, pw_salt, created_at) VALUES ('u@x.io', x'00', x'00', 'now')").lastrowid
        c.execute("INSERT INTO sessions(id, user_id, csrf, created_at, expires_at) VALUES ('s', ?, 'c', 'now', 'later')", (uid,))
        c.execute("INSERT INTO matches(source, match_key, source_url, created_by, created_at, refreshed_at) "
                  "VALUES ('fs', 'm1', 'u', ?, 'now', 'now')", (uid,))
        c.execute("DELETE FROM users WHERE id = ?", (uid,))
        self.assertEqual(c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
        self.assertIsNone(c.execute("SELECT created_by FROM matches").fetchone()[0])


@unittest.skipUnless(CLOUD_DEPS, "cần pip install -r requirements-cloud.txt")
class DataSourceTest(unittest.TestCase):
    def test_flashscore_ref_rebuilds_the_link(self):
        from cloud.datasource import FlashscoreSource
        ref = FlashscoreSource().parse_ref(" https://flashscore.com/match/football/a-AAAAAAAA/b-BBBBBBBB/?mid=CCCCCCCC&x=<script> ")
        self.assertEqual((ref.source, ref.key), ("flashscore", "CCCCCCCC"))
        self.assertEqual(ref.url, "https://www.flashscore.com/match/football/a-AAAAAAAA/b-BBBBBBBB/?mid=CCCCCCCC")

    def test_mid_is_required_and_bad_links_rejected(self):
        from cloud.datasource import FlashscoreSource
        from cloud.errors import ApiError
        from crawler.errors import CrawlError
        with self.assertRaises(ApiError):
            FlashscoreSource().parse_ref("https://www.flashscore.com/match/football/a-AAAAAAAA/b-BBBBBBBB/")
        for bad in ("http://www.flashscore.com/match/football/a/b/?mid=CCCCCCCC",
                    "https://www.flashscore.com.evil.io/match/football/a/b/?mid=CCCCCCCC",
                    "https://user@www.flashscore.com/match/football/a/b/?mid=CCCCCCCC"):
            with self.subTest(url=bad), self.assertRaises(CrawlError):
                FlashscoreSource().parse_ref(bad)


if __name__ == "__main__":
    unittest.main()
