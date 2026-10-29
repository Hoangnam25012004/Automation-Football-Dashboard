"""Bản Hugging Face: đồng bộ SQLite ↔ Dataset (giả lập bằng thư mục tạm), admin đầu tiên từ Secret, gói file Space."""
import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.cloud._harness import CLOUD_DEPS, PASSWORD

HF_DEPS = CLOUD_DEPS and importlib.util.find_spec("huggingface_hub") is not None


class FakeApi:
    """Dataset giả: upload_file chép file vào một thư mục."""

    def __init__(self, store: Path):
        self.store, self.uploads = store, 0

    def upload_file(self, path_or_fileobj, path_in_repo, repo_id, repo_type, commit_message):
        shutil.copy2(path_or_fileobj, self.store / path_in_repo)
        self.uploads += 1


@unittest.skipUnless(HF_DEPS, "cần requirements-cloud.txt + huggingface_hub")
class HfSyncTest(unittest.TestCase):
    def setUp(self):
        from cloud import config
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.store = root / "dataset"
        self.store.mkdir()
        self.settings = config.Settings()
        self.settings.db_path = root / "live" / "app.db"
        self.env = mock.patch.dict(os.environ, {"HF_TOKEN": "x", "HF_BACKUP_REPO": "user/space-data"})
        self.env.start()
        self.api = FakeApi(self.store)
        self.patch_api = mock.patch("cloud.hfsync._api", return_value=self.api)
        self.patch_api.start()

    def tearDown(self):
        self.patch_api.stop()
        self.env.stop()
        self.tmp.cleanup()

    def download(self, repo_id, filename, repo_type, token):
        from huggingface_hub.errors import EntryNotFoundError
        path = self.store / filename
        if not path.exists():
            raise EntryNotFoundError("missing")
        return str(path)

    def test_push_only_when_changed_then_restore_on_fresh_disk(self):
        from cloud import auth, hfsync
        from cloud.db import connect, migrate
        conn = connect(self.settings.db_path)
        migrate(conn)
        auth.create_admin(conn, "admin@example.com", PASSWORD)
        conn.close()
        syncer = hfsync.Syncer(self.settings)
        self.assertTrue(syncer.push())
        self.assertFalse(syncer.push())                    # không đổi ⇒ không tạo commit mới
        self.assertEqual(self.api.uploads, 1)
        # Space khởi động lại: ổ đĩa trống ⇒ khôi phục từ dataset
        for f in self.settings.db_path.parent.iterdir():
            f.unlink()
        with mock.patch("huggingface_hub.hf_hub_download", side_effect=self.download):
            self.assertTrue(hfsync.restore(self.settings))
        conn = connect(self.settings.db_path)
        self.assertEqual(conn.execute("SELECT email FROM users").fetchone()[0], "admin@example.com")
        conn.close()
        with mock.patch("huggingface_hub.hf_hub_download", side_effect=self.download):
            self.assertFalse(hfsync.restore(self.settings))  # DB cục bộ đã có ⇒ không ghi đè

    def test_restore_without_backup_starts_empty(self):
        from cloud import hfsync
        with mock.patch("huggingface_hub.hf_hub_download", side_effect=self.download):
            self.assertFalse(hfsync.restore(self.settings))
        self.assertFalse(self.settings.db_path.exists())

    def test_bootstrap_admin_only_once_and_never_overwrites(self):
        from cloud import hf_main
        from cloud.db import connect
        from cloud.security import verify_password
        with mock.patch.dict(os.environ, {"BOOTSTRAP_ADMIN_EMAIL": "boss@example.com", "BOOTSTRAP_ADMIN_PASSWORD": PASSWORD}):
            hf_main.bootstrap_admin(self.settings)
        with mock.patch.dict(os.environ, {"BOOTSTRAP_ADMIN_EMAIL": "boss@example.com", "BOOTSTRAP_ADMIN_PASSWORD": "another-password-1"}):
            hf_main.bootstrap_admin(self.settings)
        conn = connect(self.settings.db_path)
        row = conn.execute("SELECT * FROM users").fetchone()
        conn.close()
        self.assertEqual((row["email"], row["role"], row["status"]), ("boss@example.com", "admin", "active"))
        self.assertTrue(verify_password(PASSWORD, row["pw_hash"], row["pw_salt"]))


class SpaceBundleTest(unittest.TestCase):
    def test_bundle_contains_only_runtime_files(self):
        import sys
        from tests import _support
        sys.path.insert(0, str(_support.ROOT / "tools"))
        import push_hf_space
        with tempfile.TemporaryDirectory() as tmp:
            push_hf_space.stage(Path(tmp))
            names = sorted(p.name for p in Path(tmp).iterdir())
            self.assertEqual(names, ["Dockerfile", "README.md", "cloud", "crawler", "match_report.html", "requirements-cloud.txt"])
            self.assertIn("app_port: 7860", (Path(tmp) / "README.md").read_text(encoding="utf-8"))
            self.assertFalse(list(Path(tmp).rglob("__pycache__")))
            self.assertFalse(list(Path(tmp).rglob(".env")))


if __name__ == "__main__":
    unittest.main()
