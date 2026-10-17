from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def find_tesseract() -> Path | None:
    configured = os.environ.get("FOREVER_PROBE_TESSERACT")
    if configured and Path(configured).is_file():
        return Path(configured)

    located = shutil.which("tesseract")
    if located:
        return Path(located)

    roots = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
    ]
    relatives = [
        Path("Tesseract-OCR/tesseract.exe"),
        Path("Programs/Tesseract-OCR/tesseract.exe"),
    ]
    for root in filter(None, roots):
        for relative in relatives:
            candidate = Path(root) / relative
            if candidate.is_file():
                return candidate
    return None


def normalize_ocr_text(value: str) -> str:
    lines = [" ".join(line.split()) for line in value.replace("\r", "").split("\n")]
    return "\n".join(line for line in lines if line).strip()


def has_ascii_path(path: Path) -> bool:
    try:
        str(path).encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


class TesseractEngine:
    def __init__(self, executable: Path, languages: str = "eng+ces") -> None:
        self.executable = executable
        self.languages = languages

    def recognize(self, image_path: Path) -> str:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        arguments = [str(self.executable), str(image_path), "stdout"]
        bundled_data = self.executable.parent / "tessdata"
        if bundled_data.is_dir():
            arguments.extend(["--tessdata-dir", str(bundled_data)])
        arguments.extend(["-l", self.languages, "--psm", "6"])
        result = subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            check=False,
            creationflags=creation_flags,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or f"exit code {result.returncode}"
            raise RuntimeError(f"Tesseract OCR failed: {detail}")
        return normalize_ocr_text(result.stdout)

