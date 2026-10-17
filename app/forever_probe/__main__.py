from __future__ import annotations

import argparse
import os
import sys
import tkinter as tk
from pathlib import Path

from .screen_capture import enable_dpi_awareness
from .ui import ProbeWindow


def _candidate_logs() -> list[Path]:
    candidates: list[Path] = []
    for env_name in ("ProgramFiles(x86)", "ProgramFiles"):
        base_value = os.environ.get(env_name)
        if not base_value:
            continue
        wow = Path(base_value) / "World of Warcraft"
        if wow.is_dir():
            candidates.extend(wow.glob("_*_/Logs/WoWChatLog.txt"))
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline překladač chatu pro WoW")
    parser.add_argument("--log", type=Path, help="Path to WoWChatLog.txt")
    parser.add_argument("--simulate", action="store_true", help="Generate local messages")
    capture = parser.add_mutually_exclusive_group()
    capture.add_argument("--ocr", action="store_true", help="Capture text with OCR")
    capture.add_argument(
        "--optical",
        action="store_true",
        help="Decode the addon's optical data block",
    )
    parser.add_argument(
        "--from-beginning",
        action="store_true",
        help="Read an existing log from its beginning",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not (args.simulate or args.ocr or args.optical or args.log):
        args.optical = True
    log_path = args.log
    if log_path is None and not args.simulate and not (args.ocr or args.optical):
        found = _candidate_logs()
        log_path = found[0] if found else None

    enable_dpi_awareness()
    root = tk.Tk()
    ProbeWindow(
        root,
        log_path=log_path,
        simulate=args.simulate,
        start_at_end=not args.from_beginning,
        ocr_mode=args.ocr,
        optical_mode=args.optical,
    )
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

