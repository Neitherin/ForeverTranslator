from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .resources import user_data_directory


_GEOMETRY = re.compile(r"^(?P<width>\d+)x(?P<height>\d+)(?P<x>[+-]\d+)(?P<y>[+-]\d+)$")


@dataclass(slots=True)
class AppSettings:
    geometry: str = "760x520+360+120"
    always_on_top: bool = True

    @classmethod
    def load(cls, path: Path | None = None) -> "AppSettings":
        settings_path = path or user_data_directory() / "settings.json"
        try:
            value = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return cls()
        geometry = value.get("geometry")
        if not isinstance(geometry, str) or not valid_geometry(geometry):
            geometry = cls().geometry
        topmost = value.get("always_on_top", True)
        return cls(
            geometry=geometry,
            always_on_top=topmost if isinstance(topmost, bool) else True,
        )

    def save(self, path: Path | None = None) -> None:
        settings_path = path or user_data_directory() / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = settings_path.with_suffix(".tmp")
        content = json.dumps(
            {
                "geometry": self.geometry,
                "always_on_top": self.always_on_top,
            },
            ensure_ascii=False,
            indent=2,
        )
        temporary.write_text(content, encoding="utf-8")
        try:
            temporary.replace(settings_path)
        except OSError:
            # Some restricted Windows folders deny atomic replacement even when
            # ordinary writes are allowed. Keep settings usable in that case.
            settings_path.write_text(content, encoding="utf-8")
            try:
                temporary.unlink()
            except OSError:
                pass


def valid_geometry(
    value: str,
    *,
    minimum_width: int = 420,
    minimum_height: int = 300,
) -> bool:
    match = _GEOMETRY.fullmatch(value)
    if not match:
        return False
    return int(match.group("width")) >= minimum_width and int(match.group("height")) >= minimum_height
