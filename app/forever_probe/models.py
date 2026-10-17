from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ChatMessage:
    timestamp: datetime | None
    channel: str
    author: str | None
    text: str
    raw: str
    received_at: datetime
    source: str = "chat-log"

    @property
    def latency_ms(self) -> float | None:
        if self.timestamp is None:
            return None
        return max(0.0, (self.received_at - self.timestamp).total_seconds() * 1000.0)

