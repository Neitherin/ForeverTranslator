from __future__ import annotations

import unittest
from datetime import datetime

from forever_probe.parser import parse_chat_line


class ParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 17, 20, 10, 1)

    def test_parses_numbered_channel_and_czech_text(self) -> None:
        message = parse_chat_line(
            "10/17 20:10:00.125  [1. General] [Žluťoučký-Realm]: Příliš žluťoučký kůň",
            self.now,
        )
        self.assertEqual(message.channel, "GENERAL")
        self.assertEqual(message.author, "Žluťoučký-Realm")
        self.assertEqual(message.text, "Příliš žluťoučký kůň")
        self.assertEqual(message.source, "chat-log")
        self.assertAlmostEqual(message.latency_ms or 0, 875)

    def test_parses_whisper_verb_format(self) -> None:
        message = parse_chat_line(
            "10/17 20:10:00.000  Player-Realm whispers: hello", self.now
        )
        self.assertEqual(message.channel, "WHISPER")
        self.assertEqual(message.author, "Player-Realm")
        self.assertEqual(message.text, "hello")

    def test_parses_unbracketed_author(self) -> None:
        message = parse_chat_line(
            "10/17 20:10:00.000  [Guild] Player-Realm: ready", self.now
        )
        self.assertEqual(message.channel, "GUILD")
        self.assertEqual(message.author, "Player-Realm")
        self.assertEqual(message.text, "ready")

    def test_retains_unknown_format(self) -> None:
        message = parse_chat_line("a future beta format", self.now)
        self.assertEqual(message.channel, "UNKNOWN")
        self.assertEqual(message.text, "a future beta format")
        self.assertIsNone(message.timestamp)


if __name__ == "__main__":
    unittest.main()

