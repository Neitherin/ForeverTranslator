from __future__ import annotations

from pathlib import Path
from typing import Callable


class FileFollower:
    """Non-blocking byte follower that tolerates partial lines and truncation."""

    def __init__(self, path: Path, *, start_at_end: bool = True) -> None:
        self.path = path
        self.start_at_end = start_at_end
        self.offset = 0
        self._initialized = False
        self._pending = b""

    def poll(self, on_line: Callable[[str], None]) -> int:
        if not self.path.exists():
            return 0

        emitted = 0
        size = self.path.stat().st_size
        if not self._initialized:
            self.offset = size if self.start_at_end else 0
            self._initialized = True
        elif size < self.offset:
            emitted += self.flush_pending(on_line)
            self.offset = 0

        with self.path.open("rb") as stream:
            stream.seek(self.offset)
            chunk = stream.read()
            self.offset = stream.tell()

        if not chunk:
            return emitted

        data = self._pending + chunk
        parts = data.split(b"\n")
        self._pending = parts.pop()
        for part in parts:
            on_line(part.rstrip(b"\r").decode("utf-8", errors="replace"))
            emitted += 1
        return emitted

    def flush_pending(self, on_line: Callable[[str], None]) -> int:
        """Emit a final non-newline-terminated line on shutdown or rotation."""
        if not self._pending:
            return 0
        pending = self._pending
        self._pending = b""
        on_line(pending.rstrip(b"\r").decode("utf-8", errors="replace"))
        return 1

