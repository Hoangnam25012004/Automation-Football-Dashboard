"""CLI quản trị chạy trên server.

  python -m cloud.admin create-admin --email you@example.com      (hỏi mật khẩu; hoặc đặt ADMIN_PASSWORD)
  python -m cloud.admin list-users
  python -m cloud.admin set-status --email x@y.z --status active|disabled
  python -m cloud.admin reset-breaker
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

from . import auth, config, jobs
from .db import connect, migrate, tx
from .errors import ApiError


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Quản trị Match Performance (cloud)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-admin", help="tạo/khôi phục tài khoản admin")
    c.add_argument("--email", required=True)
    sub.add_parser("list-users")
    s = sub.add_parser("set-status")
    s.add_argument("--email", required=True)
    s.add_argument("--status", choices=["active", "disabled", "pending"], required=True)
    sub.add_parser("reset-breaker", help="mở lại crawl sau khi bị ngắt mạch")
    args = ap.parse_args(argv)

    settings = config.load()
    conn = connect(settings.db_path)
    migrate(conn)
    try:
        if args.cmd == "create-admin":
            password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Mật khẩu admin (≥ 10 ký tự): ")
            user_id = auth.create_admin(conn, args.email, password)
            print(f"✓ Admin #{user_id} ({args.email}) đã sẵn sàng.")
        elif args.cmd == "list-users":
            for u in auth.list_users(conn):
                print(f"{u['id']:>4}  {u['role']:<6}  {u['status']:<8}  {'✓' if u['verified'] else '·'}  {u['email']}")
        elif args.cmd == "set-status":
            with tx(conn):
                cur = conn.execute("UPDATE users SET status = ? WHERE email = ?", (args.status, args.email))
                if args.status != "active":
                    conn.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE email = ?)", (args.email,))
            print("✓ Đã cập nhật." if cur.rowcount else "✗ Không tìm thấy email.")
        elif args.cmd == "reset-breaker":
            with tx(conn):
                jobs.reset_breaker(conn, None)
            print("✓ Đã mở lại crawl.")
    except ApiError as exc:
        print(f"✗ {exc.message} {exc.hint}".strip())
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
