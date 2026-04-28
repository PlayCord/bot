"""Analytics repository methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playcord.infrastructure.db.database import Database


@dataclass(slots=True)
class AnalyticsRepository:
    database: Database

    def record_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        metadata = payload or {}
        self.database.record_analytics_event(
            event_type=event_type,
            user_id=metadata.get("user_id"),
            guild_id=metadata.get("guild_id"),
            game_type=metadata.get("game_type"),
            match_id=metadata.get("match_id"),
            metadata=(
                metadata.get("metadata")
                if isinstance(metadata.get("metadata"), dict)
                else metadata
            ),
        )

    def get_summary(self, *, hours: int = 24) -> list[dict[str, Any]]:
        return self.database.get_analytics_event_counts(hours=hours)

    def get_recent_events(self, *, hours: int = 24, limit: int = 50) -> list[Any]:
        return self.database.get_analytics_recent_events(hours=hours, limit=limit)

    def get_event_counts_by_game(self, *, hours: int = 24) -> list[dict[str, Any]]:
        return self.database.get_analytics_event_counts_by_game(hours=hours)
