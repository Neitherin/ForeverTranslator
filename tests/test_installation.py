from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from forever_probe.installation import addon_target, install_addon, validate_wow_directory


class AddonInstallationTests(unittest.TestCase):
    def test_requires_a_wow_executable(self) -> None:
        with TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "složku konkrétní verze WoW"):
                validate_wow_directory(Path(temporary))

    def test_installs_packaged_addon_files(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            wow = root / "_classic_beta_"
            wow.mkdir()
            (wow / "WowClassic.exe").touch()
            source = root / "source-addon"
            source.mkdir()
            (source / "Core.lua").write_text("-- test", encoding="utf-8")
            (source / "ForeverTranslatorProbe.toc").write_text("## test", encoding="utf-8")

            target = install_addon(wow, source=source)

            self.assertEqual(target, addon_target(wow))
            self.assertEqual((target / "Core.lua").read_text(encoding="utf-8"), "-- test")

    def test_accepts_beta_executable_name(self) -> None:
        with TemporaryDirectory() as temporary:
            wow = Path(temporary) / "_classic_beta_"
            wow.mkdir()
            (wow / "WowClassicB.exe").touch()
            validate_wow_directory(wow)

    def test_does_not_accept_crash_reporter_alone(self) -> None:
        with TemporaryDirectory() as temporary:
            wow = Path(temporary)
            (wow / "WowError.exe").touch()
            with self.assertRaises(ValueError):
                validate_wow_directory(wow)


if __name__ == "__main__":
    unittest.main()
