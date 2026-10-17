from __future__ import annotations

import shutil
from pathlib import Path

from .resources import addon_source_directory


ADDON_FOLDER = "ForeverTranslatorProbe"


def addon_target(wow_flavor_directory: Path) -> Path:
    return wow_flavor_directory / "Interface" / "AddOns" / ADDON_FOLDER


def validate_wow_directory(path: Path) -> None:
    if not path.is_dir():
        raise ValueError("Vybraná složka neexistuje.")
    executables = (
        executable
        for executable in path.glob("Wow*.exe")
        if executable.name.casefold() != "wowerror.exe"
    )
    if not any(executable.is_file() for executable in executables):
        raise ValueError(
            "Vyberte složku konkrétní verze WoW, například _retail_ nebo _classic_beta_."
        )


def install_addon(
    wow_flavor_directory: Path,
    *,
    source: Path | None = None,
) -> Path:
    validate_wow_directory(wow_flavor_directory)
    source_directory = source or addon_source_directory()
    if not (source_directory / "Core.lua").is_file():
        raise FileNotFoundError("Přibalené soubory addonu nebyly nalezeny.")
    target = addon_target(wow_flavor_directory)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_directory, target, dirs_exist_ok=True)
    return target
