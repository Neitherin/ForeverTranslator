from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from forever_probe.settings import AppSettings, valid_geometry


class SettingsTests(unittest.TestCase):
    def test_round_trip_preserves_geometry_and_topmost(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            AppSettings("640x360-20+40", False).save(path)
            self.assertEqual(AppSettings.load(path), AppSettings("640x360-20+40", False))

    def test_invalid_or_too_small_geometry_uses_default(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            path.write_text(json.dumps({"geometry": "100x80+0+0"}), encoding="utf-8")
            self.assertEqual(AppSettings.load(path).geometry, AppSettings().geometry)

    def test_geometry_validation(self) -> None:
        self.assertTrue(valid_geometry("420x300+0-12"))
        self.assertFalse(valid_geometry("419x300+0+0"))
        self.assertFalse(valid_geometry("not geometry"))


if __name__ == "__main__":
    unittest.main()
