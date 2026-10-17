from __future__ import annotations

import unittest
from unittest.mock import patch

from forever_probe.resources import model_directory, user_data_directory


class ResourceTests(unittest.TestCase):
    def test_model_names_are_direction_specific(self) -> None:
        self.assertEqual(model_directory("en-cs").name, "opus-mt-en-cs-int8")
        self.assertEqual(model_directory("cs-en").name, "opus-mt-cs-en-int8")

    def test_unknown_model_direction_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            model_directory("cs-de")

    def test_user_data_prefers_local_app_data(self) -> None:
        with patch.dict("os.environ", {"LOCALAPPDATA": "C:\\Users\\Test\\AppData\\Local"}):
            self.assertEqual(user_data_directory().name, "ForeverTranslator")


if __name__ == "__main__":
    unittest.main()
