"""Analytics service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playcord.application.repositories import AnalyticsRepositoryPort


@dataclass(slots=True)
class AnalyticsService:
    repository: AnalyticsRepositoryPort

    def record(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.repository.record_event(event_type, payload or {})

    def summary(self, *, hours: int = 24) -> list[dict[str, Any]]:
        return self.repository.get_summary(hours=hours)
