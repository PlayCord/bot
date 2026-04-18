"""Analytics repository methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playcord.utils.database import Database


@dataclass(slots=True)
class AnalyticsRepository:
    database: Database

    def record_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.database.track_analytics_event(event_type, payload or {})

    def get_summary(self, *, hours: int = 24) -> list[dict[str, Any]]:
        return self.database.get_analytics_summary(hours=hours)

    def get_recent_events(self, *, hours: int = 24, limit: int = 50) -> list[Any]:
        return self.database.get_recent_analytics_events(hours=hours, limit=limit)
