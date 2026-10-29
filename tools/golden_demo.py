"""Ghi / kiểm tra golden snapshot của luồng demo (design doc §9.3).

  python tools/golden_demo.py --write   chụp từ match_report.html HIỆN TẠI → tests/golden/demo_views.json
                                        (golden v2: chỉ ghi lại sau khi người dùng nghiệm thu giao diện)
  python tools/golden_demo.py --check   chụp từ match_report.html hiện tại và so với golden
  python tools/golden_demo.py --stability   chụp file hiện tại 2 lần, phải giống hệt nhau

Cần mạng để tải thư viện CDN (Chart.js…); Tesseract và web font bị chặn có chủ đích.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import html_guard  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from tests import _support  # noqa: E402
from tests.e2e import demo_views  # noqa: E402

GOLDEN_FILE = _support.GOLDEN / "demo_views.json"


def capture(url: str) -> tuple[dict, list[str]]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            _support.block_noise(page)
            log = _support.ConsoleLog(page)
            demo_views.open_dashboard_from_demo(page, url)
            return demo_views.capture_views(page), log.errors
        finally:
            browser.close()


def main() -> int:
    html_guard.utf8_stdout()
    ap = argparse.ArgumentParser(description="Golden snapshot của luồng demo")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--stability", action="store_true")
    args = ap.parse_args()

    if args.write:
        views, errors = capture(_support.HTML.as_uri())
        if errors:
            print("✗ Trang có lỗi JS — không ghi golden:\n  " + "\n  ".join(errors))
            return 1
        GOLDEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_FILE.write_text(json.dumps(views, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                               encoding="utf-8", newline="\n")
        charts = sum(len(v["charts"]) for v in views.values())
        print(f"✓ Đã ghi {GOLDEN_FILE.relative_to(ROOT)}: {len(views)} view, {charts} biểu đồ (từ match_report.html hiện tại)")
        return 0

    if args.stability:
        first, e1 = capture(_support.HTML.as_uri())
        second, e2 = capture(_support.HTML.as_uri())
        problems = demo_views.diff_views(first, second)
        print("✓ Hai lần chụp giống hệt nhau" if not problems else "✗ Không ổn định:\n" + "\n".join(problems))
        if e1 or e2:
            print("✗ Lỗi JS:\n  " + "\n  ".join(e1 + e2))
        return 0 if not problems and not (e1 or e2) else 1

    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    views, errors = capture(_support.HTML.as_uri())
    problems = demo_views.diff_views(golden, views)
    if errors:
        problems.append("lỗi JS trên trang:\n  " + "\n  ".join(errors))
    if problems:
        print("✗ Khác golden:\n" + "\n".join(problems))
        return 1
    print(f"✓ {len(views)} view của luồng demo giống hệt golden")
    return 0


if __name__ == "__main__":
    sys.exit(main())
