"""Hợp đồng B3 (design doc dashboard-redesign §10.2): OCR line-ups của demo cho đúng dữ liệu như trước
khi thiết kế lại (golden chụp trên mã cũ — tests/golden/demo_lineup_text.json).

Cần mạng: Chart.js + Tesseract.js (CDN) và mô hình ngôn ngữ của Tesseract.
"""
import json
import sys
import unittest

from tests import _support

sys.path.insert(0, str(_support.ROOT / "tools"))
import golden_ocr  # noqa: E402


class DemoOcrTest(unittest.TestCase):
    def test_demo_ocr_matches_golden(self):
        data, errors = golden_ocr.capture_ocr(_support.HTML.as_uri())
        self.assertEqual(errors, [])
        golden = json.loads(golden_ocr.GOLDEN_FILE.read_text(encoding="utf-8"))
        self.assertEqual(data, golden)
        self.assertEqual(len(data["formation"]["players"]), 22)


if __name__ == "__main__":
    unittest.main()
