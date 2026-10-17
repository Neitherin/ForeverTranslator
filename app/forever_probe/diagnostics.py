from __future__ import annotations

import json
import math
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .models import ChatMessage


_REPORTABLE_CHANNELS = {
    "SAY",
    "YELL",
    "WHISPER",
    "WHISPER_INFORM",
    "PARTY",
    "PARTY_LEADER",
    "RAID",
    "RAID_LEADER",
    "RAID_WARNING",
    "GUILD",
    "OFFICER",
    "INSTANCE",
    "INSTANCE_CHAT",
    "INSTANCE_CHAT_LEADER",
    "GENERAL",
    "TRADE",
    "LOOKINGFORGROUP",
    "LOCALDEFENSE",
    "EMOTE",
    "SYSTEM",
    "UNKNOWN",
}


def _report_channel(channel: str) -> str:
    normalized = channel.upper()
    return normalized if normalized in _REPORTABLE_CHANNELS else "CUSTOM_OR_OTHER"


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


@dataclass
class ProbeDiagnostics:
    source_label: str
    started_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    counts: Counter[str] = field(default_factory=Counter)
    latencies_ms: deque[float] = field(default_factory=lambda: deque(maxlen=1000))
    last_received_at: datetime | None = None
    live_messages: int = 0

    def observe(self, message: ChatMessage) -> None:
        self.counts[_report_channel(message.channel)] += 1
        self.last_received_at = message.received_at
        if message.source in {"chat-log", "ocr", "optical"}:
            self.live_messages += 1
        latency = message.latency_ms
        if latency is not None and latency < 3_600_000:
            self.latencies_ms.append(latency)

    @property
    def status(self) -> str:
        if self.live_messages == 0:
            return "UNVERIFIED"
        if self.last_received_at is None:
            return "UNVERIFIED"
        age = (datetime.now().astimezone() - self.last_received_at).total_seconds()
        return "RECEIVING" if age < 30 else "STALE"

    def summary(self) -> dict[str, object]:
        values = list(self.latencies_ms)
        return {
            "schema_version": 1,
            "source": self.source_label,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "last_received_at": (
                self.last_received_at.isoformat() if self.last_received_at else None
            ),
            "message_count": sum(self.counts.values()),
            "channel_counts": dict(sorted(self.counts.items())),
            "latency_ms": {
                "samples": len(values),
                "p50": _percentile(values, 0.50),
                "p95": _percentile(values, 0.95),
            },
            "privacy": "No message text or player names are included.",
        }

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps(self.summary(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

