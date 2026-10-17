from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from forever_probe.translation import (
    OfflineTranslator,
    OcrChatMessage,
    format_ocr_message,
    normalize_chat_text,
    normalize_channel,
    parse_ocr_messages,
    parse_wow_text,
    plain_wow_text,
)
from forever_probe.ui import channel_color, channel_label, class_color


class TranslationParsingTests(unittest.TestCase):
    def test_parses_and_joins_wrapped_ocr_messages(self) -> None:
        text = (
            "[WHISPER. INFORM] Healya: ted píšu sám sobě takže to duplicitní bude, ale\n"
            "jinak asi dobrý\n"
            "[CHANNEL] Fanny: is the little zone map new?"
        )

        self.assertEqual(
            parse_ocr_messages(text),
            [
                OcrChatMessage("CHANNEL", "Fanny", "is the little zone map new?"),
                OcrChatMessage(
                    "WHISPER_INFORM",
                    "Healya",
                    "ted píšu sám sobě takže to duplicitní bude, ale jinak asi dobrý",
                ),
            ],
        )

    def test_ignores_noise_before_first_message(self) -> None:
        self.assertEqual(parse_ocr_messages("Forever Translator Probe\nno messages"), [])

    def test_formats_message_without_empty_author(self) -> None:
        message = OcrChatMessage("SYSTEM", None, "Player has left the guild.")
        self.assertEqual(
            format_ocr_message(message), "[SYSTEM] Player has left the guild."
        )

    def test_normalizes_ocr_channel_separator(self) -> None:
        self.assertEqual(normalize_channel(" whisper. inform "), "WHISPER_INFORM")

    def test_rejects_unknown_translation_direction_before_loading_runtime(self) -> None:
        with self.assertRaisesRegex(ValueError, "Nepodporovaný směr"):
            OfflineTranslator("de-cs")

    def test_reports_missing_direction_model(self) -> None:
        with TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(FileNotFoundError, "CS-EN"):
                OfflineTranslator("cs-en", Path(temporary))

    def test_wow_channel_colors_cover_primary_chat_types(self) -> None:
        self.assertEqual(channel_color("party"), "#AAAFFF")
        self.assertEqual(channel_color("guild"), "#40FF40")
        self.assertEqual(channel_color("channel"), "#F4B7A8")
        self.assertEqual(channel_color("whisper"), "#FF80FF")
        self.assertEqual(channel_color("yell"), "#FF3F40")
        self.assertEqual(channel_color("unknown"), "#F0F0F0")

    def test_chat_shorthand_is_expanded_only_for_incoming_english(self) -> None:
        self.assertEqual(
            normalize_chat_text("thx, lfg world buffs; nerfing crits pls", "en-cs"),
            "thanks, looking for group world bonuses; weakening critical hits please",
        )
        self.assertEqual(normalize_chat_text("U lesa", "cs-en"), "U lesa")

    def test_clean_channel_labels(self) -> None:
        self.assertEqual(channel_label("CHANNEL"), "World")
        self.assertEqual(channel_label("WHISPER"), "/w")
        self.assertEqual(channel_label("custom_event"), "Custom Event")

    def test_wow_class_colors(self) -> None:
        self.assertEqual(class_color("mage"), "#3FC7EB")
        self.assertEqual(class_color("ROGUE"), "#FFF468")
        self.assertIsNone(class_color(None))
        self.assertIsNone(class_color("UNKNOWN"))

    def test_parses_colored_wow_item_link(self) -> None:
        raw = (
            "tipsy from the "
            "|cff1eff00|Hitem:2723::::::::30:1487:::::::::|h[Bottle of Dalaran Noir]|h|r."
        )
        segments = parse_wow_text(raw)
        self.assertEqual(plain_wow_text(raw), "tipsy from the [Bottle of Dalaran Noir].")
        self.assertEqual(segments[1].text, "[Bottle of Dalaran Noir]")
        self.assertEqual(segments[1].link_type, "item")
        self.assertEqual(segments[1].color, "#1eff00")

    def test_parses_multiple_uncolored_wow_link_types(self) -> None:
        raw = "Do |Hquest:42:10|h[A Noble Brew]|h for |Hcreature:123|h[John]|h."
        links = [segment for segment in parse_wow_text(raw) if segment.is_link]
        self.assertEqual([link.link_type for link in links], ["quest", "creature"])
        self.assertEqual(plain_wow_text(raw), "Do [A Noble Brew] for [John].")

    def test_parses_modern_named_item_quality_color(self) -> None:
        raw = "|cnIQ3:|Hitem:19019::::::::|h[Thunderfury]|h|r"
        segment = parse_wow_text(raw)[0]
        self.assertEqual(segment.text, "[Thunderfury]")
        self.assertEqual(segment.link_type, "item")
        self.assertEqual(segment.color, "#0070dd")

    def test_translation_preserves_raw_link_and_translates_surrounding_text(self) -> None:
        raw_link = "|cff1eff00|Hitem:2723::::::::|h[Bottle of Dalaran Noir]|h|r"
        translator = object.__new__(OfflineTranslator)
        translator._direction = "en-cs"
        translator._translate_plain_batch = lambda texts: [
            f"CZ<{text}>" for text in texts
        ]
        translated = translator.translate_batch([f"tipsy from the {raw_link} today"])[0]
        self.assertEqual(
            translated,
            f"CZ<tipsy from the> {raw_link} CZ<today>",
        )

    def test_plain_text_is_unchanged_by_wow_parser(self) -> None:
        text = "Use [brackets] in ordinary chat."
        self.assertEqual(plain_wow_text(text), text)
        self.assertFalse(parse_wow_text(text)[0].is_link)

    def test_non_link_color_codes_are_hidden_from_translation(self) -> None:
        translator = object.__new__(OfflineTranslator)
        translator._direction = "en-cs"
        seen: list[str] = []
        translator._translate_plain_batch = lambda texts: seen.extend(texts) or texts
        translated = translator.translate_batch(["|cffff0000Danger|r!"])[0]
        self.assertEqual(seen, ["Danger!"])
        self.assertEqual(translated, "Danger!")

    def test_other_wow_controls_do_not_leak_into_display_text(self) -> None:
        raw = (
            "|TInterface\\Icons\\INV_Misc_QuestionMark:16|t "
            "Ready|n|A:communities-icon-chat:12:12|a "
            "|Hitem:123|h[Incomplete link]"
        )
        self.assertEqual(plain_wow_text(raw), " Ready\n [Incomplete link]")


if __name__ == "__main__":
    unittest.main()
