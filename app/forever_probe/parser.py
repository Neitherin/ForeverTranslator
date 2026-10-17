from __future__ import annotations

import re
from datetime import datetime

from .models import ChatMessage


_PREFIX = re.compile(
    r"^(?P<month>\d{1,2})/(?P<day>\d{1,2})\s+"
    r"(?P<clock>\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)\s{2,}(?P<body>.*)$"
)

_BRACKETED = re.compile(
    r"^\[(?P<channel>[^\]]+)\]\s+\[(?P<author>[^\]]+)\]:\s*(?P<text>.*)$"
)
_CHANNEL_AUTHOR = re.compile(
    r"^\[(?P<channel>[^\]]+)\]\s+(?P<author>[^:]+):\s*(?P<text>.*)$"
)
_CHANNEL_NUMBER = re.compile(
    r"^\[(?P<number>\d+)\.\s*(?P<channel>[^\]]+)\]\s+"
    r"\[(?P<author>[^\]]+)\]:\s*(?P<text>.*)$"
)
_VERB = re.compile(
    r"^(?P<author>.+?)\s+(?P<verb>whispers|says|yells|emotes):\s*(?P<text>.*)$",
    re.IGNORECASE,
)

_VERB_CHANNELS = {
    "whispers": "WHISPER",
    "says": "SAY",
    "yells": "YELL",
    "emotes": "EMOTE",
}


def _nearest_timestamp(match: re.Match[str], received_at: datetime) -> datetime | None:
    clock = match.group("clock")
    fmt = "%Y %m %d %H:%M:%S.%f" if "." in clock else "%Y %m %d %H:%M:%S"
    candidates: list[datetime] = []
    for year in (received_at.year - 1, received_at.year, received_at.year + 1):
        try:
            value = datetime.strptime(
                f"{year} {match.group('month')} {match.group('day')} {clock}", fmt
            )
            if received_at.tzinfo is not None:
                value = value.replace(tzinfo=received_at.tzinfo)
            candidates.append(value)
        except ValueError:
            continue
    return min(candidates, key=lambda item: abs(item - received_at)) if candidates else None


def parse_chat_line(line: str, received_at: datetime | None = None) -> ChatMessage:
    received = received_at or datetime.now().astimezone()
    raw = line.rstrip("\r\n")
    prefix = _PREFIX.match(raw)
    if prefix:
        timestamp = _nearest_timestamp(prefix, received)
        body = prefix.group("body")
    else:
        timestamp = None
        body = raw

    numbered = _CHANNEL_NUMBER.match(body)
    if numbered:
        return ChatMessage(
            timestamp,
            numbered.group("channel").upper(),
            numbered.group("author"),
            numbered.group("text"),
            raw,
            received,
            source="chat-log",
        )

    bracketed = _BRACKETED.match(body)
    if bracketed:
        return ChatMessage(
            timestamp,
            bracketed.group("channel").upper(),
            bracketed.group("author"),
            bracketed.group("text"),
            raw,
            received,
            source="chat-log",
        )

    channel_author = _CHANNEL_AUTHOR.match(body)
    if channel_author:
        return ChatMessage(
            timestamp,
            channel_author.group("channel").upper(),
            channel_author.group("author"),
            channel_author.group("text"),
            raw,
            received,
            source="chat-log",
        )

    verb = _VERB.match(body)
    if verb:
        return ChatMessage(
            timestamp,
            _VERB_CHANNELS[verb.group("verb").lower()],
            verb.group("author"),
            verb.group("text"),
            raw,
            received,
            source="chat-log",
        )

    return ChatMessage(
        timestamp, "UNKNOWN", None, body, raw, received, source="chat-log"
    )

