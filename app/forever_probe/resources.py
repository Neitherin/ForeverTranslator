from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIRECTORY_NAME = "ForeverTranslator"


def resource_root() -> Path:
    """Return the read-only asset root in source and frozen builds."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[2]


def user_data_directory() -> Path:
    """Return the per-user writable directory without touching the filesystem."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_DIRECTORY_NAME
    return Path.home() / f".{APP_DIRECTORY_NAME.lower()}"


def model_directory(direction: str) -> Path:
    names = {
        "en-cs": "opus-mt-en-cs-int8",
        "cs-en": "opus-mt-cs-en-int8",
    }
    try:
        name = names[direction]
    except KeyError as error:
        raise ValueError(f"Nepodporovaný směr překladu: {direction}") from error
    return resource_root() / "models" / name


def addon_source_directory() -> Path:
    return resource_root() / "addon" / "ForeverTranslatorProbe"
