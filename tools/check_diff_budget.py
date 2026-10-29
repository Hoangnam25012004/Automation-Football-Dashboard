"""Liệt kê mọi khối thay đổi của match_report.html so với baseline và gán mã RD1–RD8.

Khối nào nằm ngoài các cửa sổ được phép (design doc dashboard-redesign §10.1) ⇒ thất bại.
Chạy:  python tools/check_diff_budget.py [--baseline <git-rev>] [--show]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import html_guard  # noqa: E402


def clip(line: str, n: int = 110) -> str:
    return line if len(line) <= n else line[:n] + f"… (+{len(line) - n} ký tự)"


def main() -> int:
    html_guard.utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--baseline", help="git revision của baseline (mặc định: tag redesign-baseline)")
    ap.add_argument("--show", action="store_true", help="in nội dung từng khối")
    args = ap.parse_args()
    base = html_guard.load_baseline(args.baseline)
    cur = html_guard.load_current()
    ok, hunks = html_guard.diff_budget(base, cur)
    if not hunks:
        print("Không có thay đổi nào so với baseline.")
        return 0
    for h in hunks:
        where = f"baseline dòng {h.i1 + 1}-{h.i2}" if h.i2 > h.i1 else f"chèn trước baseline dòng {h.i1 + 1}"
        mark = "✓" if h.eid else "✗"
        print(f"{mark} [{h.eid or 'NGOÀI PHẠM VI'}] {h.tag:7s} {where}: -{len(h.removed)} +{len(h.added)} dòng")
        if args.show or not h.eid:
            for line in h.removed:
                print("    - " + clip(line))
            for line in h.added:
                print("    + " + clip(line))
    used = sorted({h.eid for h in hunks if h.eid})
    print(f"\nMã đã dùng: {', '.join(used) or '(không)'}")
    print("KẾT QUẢ: " + ("mọi thay đổi nằm trong Change surface RD1–RD8 (redesign §10.1 + cloud §11)" if ok else "CÓ THAY ĐỔI NGOÀI PHẠM VI"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
