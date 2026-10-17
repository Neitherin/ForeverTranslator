from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from forever_probe.tailer import FileFollower


class FileFollowerTests(unittest.TestCase):
    def test_emits_complete_lines_and_preserves_partial_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "WoWChatLog.txt"
            path.write_bytes("první\ndru".encode("utf-8"))
            follower = FileFollower(path, start_at_end=False)
            lines: list[str] = []

            self.assertEqual(follower.poll(lines.append), 1)
            self.assertEqual(lines, ["první"])

            with path.open("ab") as stream:
                stream.write("há\n".encode("utf-8"))
            self.assertEqual(follower.poll(lines.append), 1)
            self.assertEqual(lines, ["první", "druhá"])

    def test_start_at_end_ignores_existing_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "WoWChatLog.txt"
            path.write_text("old\n", encoding="utf-8")
            follower = FileFollower(path, start_at_end=True)
            lines: list[str] = []
            self.assertEqual(follower.poll(lines.append), 0)
            with path.open("a", encoding="utf-8") as stream:
                stream.write("new\n")
            self.assertEqual(follower.poll(lines.append), 1)
            self.assertEqual(lines, ["new"])

    def test_flushes_final_line_without_newline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "WoWChatLog.txt"
            path.write_text("final", encoding="utf-8")
            follower = FileFollower(path, start_at_end=False)
            lines: list[str] = []
            self.assertEqual(follower.poll(lines.append), 0)
            self.assertEqual(follower.flush_pending(lines.append), 1)
            self.assertEqual(lines, ["final"])
            self.assertEqual(follower.flush_pending(lines.append), 0)


if __name__ == "__main__":
    unittest.main()

