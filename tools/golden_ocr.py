"""Golden của OCR line-ups trong luồng demo (hợp đồng B3, design doc redesign §10.2).

  python tools/golden_ocr.py --write   chạy demo trên match_report.html hiện tại → tests/golden/demo_lineup_text.json
  python tools/golden_ocr.py --check   chạy lại và so với golden

Chỉ so DỮ LIỆU (`state.lineupText` sau OCR), không so DOM ⇒ dùng được trước và sau khi thiết kế lại
giao diện. Cần mạng: Chart.js + Tesseract.js (CDN) và mô hình ngôn ngữ của Tesseract.
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

GOLDEN_FILE = _support.GOLDEN / "demo_lineup_text.json"
OCR_TIMEOUT_MS = 240_000


def capture_ocr(url: str) -> tuple[dict | None, list[str]]:
    """Mở demo, mở view chứa Line-ups (id nội bộ 'overall' ở cả bản cũ lẫn bản mới) và chờ OCR xong."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            log = _support.ConsoleLog(page)
            page.goto(url, wait_until="load")
            page.wait_for_function("typeof App !== 'undefined' && typeof Chart !== 'undefined'")
            page.evaluate("App.loadDemo()")
            page.wait_for_selector("#dashboard.active", timeout=15000)
            page.evaluate("App.setTab('overall')")
            page.wait_for_function("state.lineupText !== null", timeout=OCR_TIMEOUT_MS)
            return page.evaluate("JSON.parse(JSON.stringify(state.lineupText))"), log.errors
        finally:
            browser.close()


def main() -> int:
    html_guard.utf8_stdout()
    ap = argparse.ArgumentParser(description="Golden OCR line-ups của luồng demo")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = ap.parse_args()
    data, errors = capture_ocr(_support.HTML.as_uri())
    if errors:
        print("✗ Lỗi JS:\n  " + "\n  ".join(errors))
        return 1
    if args.write:
        GOLDEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                               encoding="utf-8", newline="\n")
        print(f"✓ Đã ghi {GOLDEN_FILE.relative_to(ROOT)}: {len(data.get('formation', {}).get('players', []))} cầu thủ trên sơ đồ")
        return 0
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    if golden != data:
        print("✗ Kết quả OCR khác golden")
        return 1
    print("✓ OCR line-ups của demo giống hệt golden")
    return 0


if __name__ == "__main__":
    sys.exit(main())
