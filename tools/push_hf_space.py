"""Đẩy bản cloud lên một Hugging Face Docker Space (dùng tài khoản đã đăng nhập trên máy này).

  python tools/push_hf_space.py --admin-email ban@example.com [--space match-performance]

- Gom đúng các file cần (crawler/, cloud/, match_report.html, requirements-cloud.txt, deploy/hf/*) vào thư mục tạm
  và upload — không đẩy tests/, docs/, data/, .env hay bất kỳ bí mật nào.
- Tạo Space public (SDK docker) + Dataset riêng tư "<space>-data" để lưu bền dữ liệu.
- Đặt Variables (không bí mật) và Secret HF_TOKEN (token đang đăng nhập — dùng để ghi Dataset).
- KHÔNG đặt mật khẩu admin: bạn tự nhập Secret BOOTSTRAP_ADMIN_PASSWORD trong Settings của Space.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def stage(target: Path) -> None:
    shutil.copytree(ROOT / "crawler", target / "crawler", ignore=IGNORE)
    shutil.copytree(ROOT / "cloud", target / "cloud", ignore=IGNORE)
    for name in ("match_report.html", "requirements-cloud.txt"):
        shutil.copy2(ROOT / name, target / name)
    shutil.copy2(ROOT / "deploy" / "hf" / "Dockerfile", target / "Dockerfile")
    shutil.copy2(ROOT / "deploy" / "hf" / "README.md", target / "README.md")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--space", default="match-performance")
    ap.add_argument("--admin-email", required=True, help="email của admin đầu tiên (BOOTSTRAP_ADMIN_EMAIL)")
    ap.add_argument("--no-token-secret", action="store_true", help="không đặt Secret HF_TOKEN (tự đặt token fine-grained)")
    args = ap.parse_args()

    from huggingface_hub import HfApi, get_token
    token = get_token()
    if not token:
        print("✗ Chưa đăng nhập Hugging Face. Chạy:  python -c \"from huggingface_hub import login; login()\"")
        return 1
    api = HfApi(token=token)
    user = api.whoami()["name"]
    space_id, data_id = f"{user}/{args.space}", f"{user}/{args.space}-data"

    api.create_repo(space_id, repo_type="space", space_sdk="docker", visibility="public", exist_ok=True)
    # huggingface_hub 2.x bỏ qua `private=` ⇒ dùng `visibility` và kiểm tra lại (Dataset chứa dữ liệu người dùng)
    api.create_repo(data_id, repo_type="dataset", visibility="private", exist_ok=True)
    if not api.repo_info(data_id, repo_type="dataset").private:
        api.update_repo_settings(data_id, repo_type="dataset", visibility="private")
    assert api.repo_info(data_id, repo_type="dataset").private, "Dataset sao lưu phải là private"
    variables = {
        "HF_BACKUP_REPO": data_id, "HF_SYNC_MINUTES": "10", "REGISTRATION": "approval", "TZ": "Asia/Ho_Chi_Minh",
        "QUOTA_USER_DAILY": "10", "QUOTA_GLOBAL_HOURLY": "30", "QUEUE_MAX": "20", "REFRESH_COOLDOWN_H": "6",
        # 2 vCPU: tải song song làm menu chọn đội không mở kịp (kiểm chứng: =3 lỗi 9/9, =1 thành công 9/9)
        "FS_PARALLEL": "1", "BOOTSTRAP_ADMIN_EMAIL": args.admin_email,
    }
    for key, value in variables.items():
        api.add_space_variable(space_id, key, value)
    if not args.no_token_secret:
        api.add_space_secret(space_id, "HF_TOKEN", token, description="ghi Dataset sao lưu (cloud/hfsync.py)")

    with tempfile.TemporaryDirectory(prefix="hf-space-") as tmp:
        stage(Path(tmp))
        api.upload_folder(folder_path=tmp, repo_id=space_id, repo_type="space",
                          commit_message="Deploy Match Performance (cloud)", delete_patterns=["*"])
    host = f"{user}-{args.space}".lower().replace("_", "-").replace(".", "-")
    print(f"✓ Space: https://huggingface.co/spaces/{space_id}")
    print(f"✓ Ứng dụng (sau khi build xong ~5–10 phút): https://{host}.hf.space")
    print(f"✓ Dataset sao lưu (riêng tư): https://huggingface.co/datasets/{data_id}")
    print("→ Việc còn lại: Settings của Space → New secret → BOOTSTRAP_ADMIN_PASSWORD (≥ 10 ký tự).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
