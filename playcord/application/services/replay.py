"""Replay service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playcord.infrastructure.database import ReplayRepository


@dataclass(slots=True)
class ReplayService:
    repository: ReplayRepository

    def get_events(self, match_id: int) -> list[dict[str, Any]]:
        return self.repository.get_events(match_id)

    def append_event(
        self, match_id: int, event_type: str, payload: dict[str, Any],
    ) -> None:
        self.repository.append_event(match_id, event_type, payload)
