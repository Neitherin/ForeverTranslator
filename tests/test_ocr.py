from __future__ import annotations

import unittest

from pathlib import Path

from forever_probe.ocr import has_ascii_path, normalize_ocr_text
from forever_probe.screen_capture import ScreenRegion


class OcrTests(unittest.TestCase):
    def test_normalizes_whitespace_but_keeps_lines(self) -> None:
        self.assertEqual(
            normalize_ocr_text("  First   line\r\n\n Second\tline  \n"),
            "First line\nSecond line",
        )

    def test_region_normalizes_drag_direction(self) -> None:
        region = ScreenRegion.from_corners(300, 220, 100, 20)
        self.assertEqual(region, ScreenRegion(100, 20, 200, 200))
        self.assertTrue(region.valid)

    def test_detects_non_ascii_engine_path(self) -> None:
        self.assertTrue(has_ascii_path(Path("D:/Tesseract-OCR/tesseract.exe")))
        self.assertFalse(has_ascii_path(Path("D:/Stažené/tesseract.exe")))


if __name__ == "__main__":
    unittest.main()
