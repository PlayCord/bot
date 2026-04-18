"""Replay events and recorder protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


class ReplayRecorder(Protocol):
    """Protocol implemented by replay writers."""

    def record(self, event: "ReplayEvent") -> None:
        """Persist one replay event."""


@dataclass(frozen=True, slots=True)
class ReplayEvent:
    """A structured replay event."""

    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
