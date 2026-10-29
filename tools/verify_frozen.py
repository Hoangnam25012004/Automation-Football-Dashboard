"""Kiểm tra các vùng đóng băng của match_report.html còn giống baseline từng ký tự.

Chạy:  python tools/verify_frozen.py [--baseline <git-rev>]
Thoát mã 0 nếu mọi vùng giữ nguyên, 1 nếu có vùng bị đổi.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import html_guard  # noqa: E402


def main() -> int:
    html_guard.utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--baseline", help="git revision của baseline (mặc định: tag redesign-baseline)")
    args = ap.parse_args()
    base = html_guard.load_baseline(args.baseline)
    cur = html_guard.load_current()
    results = html_guard.check_frozen(base, cur)
    width = max(len(name) for name, _, _ in results)
    for name, ok, detail in results:
        print(f"{'✓' if ok else '✗'} {name:<{width}}  {detail}")
    bad = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} vùng đóng băng giữ nguyên.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
