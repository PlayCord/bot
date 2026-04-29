"""Analytics service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playcord.infrastructure.database import AnalyticsRepository


@dataclass(slots=True)
class AnalyticsService:
    repository: AnalyticsRepository

    def record(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.repository.record_event(event_type, payload or {})

    def summary(self, *, hours: int = 24) -> list[dict[str, Any]]:
        return self.repository.get_summary(hours=hours)
