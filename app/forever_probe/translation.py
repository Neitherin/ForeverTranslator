from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .resources import model_directory

MODEL_DIRECTORY = model_directory("en-cs")

_MESSAGE_START = re.compile(
    r"^\[(?P<channel>[^\]]+)\]\s*(?P<author>[^:]*):\s*(?P<text>.*)$"
)
_CHANNEL_SEPARATORS = re.compile(r"[.\s]+")
_SPECIAL_TOKENS = {"</s>", "<pad>", "<unk>"}
_WOW_LINK = re.compile(
    r"(?:(?P<color>\|c[0-9a-fA-F]{8})|(?P<named_color>\|cn(?P<color_name>[^:|]+):))?"
    r"(?P<link>\|H(?P<link_type>[^:|]+)(?::[^|]*)?\|h"
    r"(?P<label>.*?)\|h(?:\|r)?)"
)
_WOW_FORMATTING = re.compile(
    r"\|T[^|]*\|t|\|A[^|]*\|a|"
    r"\|c[0-9a-fA-F]{8}|\|cn[^:|]+:|\|r|"
    r"\|H[^|]*\|h|\|h"
)
_WOW_NAMED_COLORS = {
    "IQ0": "#9d9d9d",
    "IQ1": "#ffffff",
    "IQ2": "#1eff00",
    "IQ3": "#0070dd",
    "IQ4": "#a335ee",
    "IQ5": "#ff8000",
    "IQ6": "#e6cc80",
    "IQ7": "#00ccff",
    "IQ8": "#00ccff",
}

_EN_CHAT_EXPANSIONS = (
    (re.compile(r"\b(?:pls|plz)\b", re.IGNORECASE), "please"),
    (re.compile(r"\bthx\b", re.IGNORECASE), "thanks"),
    (re.compile(r"\bty\b", re.IGNORECASE), "thank you"),
    (re.compile(r"\bidk\b", re.IGNORECASE), "I do not know"),
    (re.compile(r"\bimo\b", re.IGNORECASE), "in my opinion"),
    (re.compile(r"\blfg\b", re.IGNORECASE), "looking for group"),
    (re.compile(r"\blfm\b", re.IGNORECASE), "looking for more"),
    (re.compile(r"\bu\b", re.IGNORECASE), "you"),
    (re.compile(r"\bur\b", re.IGNORECASE), "your"),
    (re.compile(r"\bcrits\b", re.IGNORECASE), "critical hits"),
    (re.compile(r"\bcrit\b", re.IGNORECASE), "critical hit"),
    (re.compile(r"\bnerfing\b", re.IGNORECASE), "weakening"),
    (re.compile(r"\bnerfed\b", re.IGNORECASE), "weakened"),
    (re.compile(r"\bnerfs\b", re.IGNORECASE), "weakens"),
    (re.compile(r"\bworld buffs\b", re.IGNORECASE), "world bonuses"),
)


@dataclass(frozen=True, slots=True)
class OcrChatMessage:
    channel: str
    author: str | None
    text: str
    player_class: str | None = None

    @property
    def cache_key(self) -> tuple[str, str | None, str]:
        return self.channel, self.author, self.text


@dataclass(frozen=True, slots=True)
class WowTextSegment:
    text: str
    raw: str
    link_type: str | None = None
    color: str | None = None

    @property
    def is_link(self) -> bool:
        return self.link_type is not None


def parse_wow_text(text: str) -> tuple[WowTextSegment, ...]:
    """Split WoW chat text into plain text and display-safe hyperlink segments."""
    segments: list[WowTextSegment] = []
    cursor = 0
    for match in _WOW_LINK.finditer(text):
        if match.start() > cursor:
            raw = text[cursor : match.start()]
            segments.append(WowTextSegment(_clean_wow_formatting(raw), raw))
        raw_link = match.group(0)
        label = _clean_wow_formatting(match.group("label"))
        color_code = match.group("color")
        color = (
            f"#{color_code[-6:]}"
            if color_code
            else _WOW_NAMED_COLORS.get((match.group("color_name") or "").upper())
        )
        segments.append(
            WowTextSegment(label, raw_link, match.group("link_type").lower(), color)
        )
        cursor = match.end()
    if cursor < len(text):
        raw = text[cursor:]
        segments.append(WowTextSegment(_clean_wow_formatting(raw), raw))
    return tuple(segments) or (WowTextSegment(_clean_wow_formatting(text), text),)


def _clean_wow_formatting(text: str) -> str:
    return _WOW_FORMATTING.sub("", text.replace("|n", "\n"))


def plain_wow_text(text: str) -> str:
    return "".join(segment.text for segment in parse_wow_text(text))


def normalize_channel(value: str) -> str:
    return _CHANNEL_SEPARATORS.sub("_", value.strip()).upper()


def parse_ocr_messages(text: str) -> list[OcrChatMessage]:
    """Parse the addon's snapshot into oldest-first messages for chat rendering."""
    messages: list[OcrChatMessage] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _MESSAGE_START.match(line)
        if match:
            author = match.group("author").strip() or None
            messages.append(
                OcrChatMessage(
                    normalize_channel(match.group("channel")),
                    author,
                    match.group("text").strip(),
                )
            )
        elif messages:
            previous = messages[-1]
            messages[-1] = OcrChatMessage(
                previous.channel,
                previous.author,
                f"{previous.text} {line}".strip(),
            )
    return list(reversed(messages))


def format_ocr_message(message: OcrChatMessage) -> str:
    author = f"{message.author}: " if message.author else ""
    return f"[{message.channel}] {author}{message.text}"


def normalize_chat_text(text: str, direction: str) -> str:
    """Expand only unambiguous English chat shorthand before translation."""
    if direction != "en-cs":
        return text
    normalized = text
    for pattern, replacement in _EN_CHAT_EXPANSIONS:
        normalized = pattern.sub(replacement, normalized)
    return normalized


class OfflineTranslator:
    """Small CPU-only translation runtime backed by an INT8 CTranslate2 model."""

    def __init__(
        self,
        direction: str = "en-cs",
        model_path: Path | None = None,
    ) -> None:
        if direction not in {"en-cs", "cs-en"}:
            raise ValueError(f"Nepodporovaný směr překladu: {direction}")
        selected_model = model_path or model_directory(direction)
        if not (selected_model / "model.bin").is_file():
            raise FileNotFoundError(
                f"Model pro {direction.upper()} nebyl nalezen v {selected_model}."
            )
        self._direction = direction
        try:
            import ctranslate2
            import sentencepiece
        except ImportError as error:
            raise RuntimeError(
                "Chybí překladové knihovny. Spusťte setup_translation.ps1."
            ) from error

        self._source = sentencepiece.SentencePieceProcessor(
            model_file=str(selected_model / "source.spm")
        )
        self._target = sentencepiece.SentencePieceProcessor(
            model_file=str(selected_model / "target.spm")
        )
        self._translator = ctranslate2.Translator(
            str(selected_model),
            device="cpu",
            compute_type="int8",
            inter_threads=1,
            intra_threads=4,
        )

    def translate_batch(self, texts: Iterable[str]) -> list[str]:
        source_texts = list(texts)
        if not source_texts:
            return []
        plans: list[list[tuple[str, str, str]]] = []
        translatable: list[str] = []
        for text in source_texts:
            plan: list[tuple[str, str, str]] = []
            for segment in parse_wow_text(text):
                if segment.is_link:
                    plan.append(("link", segment.raw, ""))
                    continue
                padding = re.fullmatch(r"(\s*)(.*?)(\s*)", segment.text, re.DOTALL)
                assert padding is not None
                leading, core, trailing = padding.groups()
                if core:
                    plan.append(("text", leading, trailing))
                    translatable.append(normalize_chat_text(core, self._direction))
                else:
                    plan.append(("literal", segment.text, ""))
            plans.append(plan)

        translated_parts = iter(self._translate_plain_batch(translatable))
        translations: list[str] = []
        for plan in plans:
            result: list[str] = []
            for kind, first, second in plan:
                if kind == "text":
                    result.append(f"{first}{next(translated_parts)}{second}")
                else:
                    result.append(first)
            translations.append("".join(result).strip())
        return translations

    def _translate_plain_batch(self, source_texts: list[str]) -> list[str]:
        if not source_texts:
            return []
        token_batches = [
            [*self._source.encode(text, out_type=str), "</s>"]
            for text in source_texts
        ]
        results = self._translator.translate_batch(
            token_batches,
            beam_size=4,
            max_decoding_length=160,
        )
        translations: list[str] = []
        for result in results:
            pieces = [
                token for token in result.hypotheses[0] if token not in _SPECIAL_TOKENS
            ]
            translations.append(self._target.decode(pieces).strip())
        return translations
