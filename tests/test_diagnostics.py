from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from forever_probe.diagnostics import ProbeDiagnostics
from forever_probe.models import ChatMessage


class DiagnosticsTests(unittest.TestCase):
    def test_report_excludes_message_and_author(self) -> None:
        now = datetime.now(timezone.utc)
        message = ChatMessage(
            timestamp=now - timedelta(milliseconds=120),
            channel="GUILD",
            author="SecretPlayer",
            text="private message",
            raw="private raw line",
            received_at=now,
        )
        diagnostics = ProbeDiagnostics("test")
        diagnostics.observe(message)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            diagnostics.save(path)
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)

        self.assertNotIn("SecretPlayer", raw)
        self.assertNotIn("private message", raw)
        self.assertEqual(data["channel_counts"], {"GUILD": 1})
        self.assertEqual(data["latency_ms"]["p50"], 120.0)

    def test_simulation_does_not_mark_live_source_verified(self) -> None:
        now = datetime.now(timezone.utc)
        diagnostics = ProbeDiagnostics("simulation")
        diagnostics.observe(
            ChatMessage(now, "SAY", "Tester", "text", "raw", now, "simulation")
        )
        self.assertEqual(diagnostics.status, "UNVERIFIED")

    def test_custom_channel_name_is_not_written_to_report(self) -> None:
        now = datetime.now(timezone.utc)
        diagnostics = ProbeDiagnostics("test")
        diagnostics.observe(
            ChatMessage(now, "My Secret Group", "Tester", "text", "raw", now)
        )
        summary = diagnostics.summary()
        self.assertEqual(summary["channel_counts"], {"CUSTOM_OR_OTHER": 1})
        self.assertNotIn("My Secret Group", json.dumps(summary))

    def test_ocr_marks_source_as_receiving(self) -> None:
        now = datetime.now(timezone.utc)
        diagnostics = ProbeDiagnostics("ocr")
        diagnostics.observe(ChatMessage(None, "OCR", None, "hello", "hello", now, "ocr"))
        self.assertEqual(diagnostics.status, "RECEIVING")

    def test_optical_marks_source_as_receiving(self) -> None:
        now = datetime.now(timezone.utc)
        diagnostics = ProbeDiagnostics("optical")
        diagnostics.observe(
            ChatMessage(None, "PARTY", "Tank", "wait", "wait", now, "optical")
        )
        self.assertEqual(diagnostics.status, "RECEIVING")


if __name__ == "__main__":
    unittest.main()
