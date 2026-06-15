"""Analytics events and rollups."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from playcord.infrastructure.config import get_settings

if TYPE_CHECKING:
    from playcord.infrastructure.database.implementation.database import Database


@dataclass(slots=True)
class AnalyticsRepository:
    database: Database
    games: Any  # GameRepository

    def record_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        metadata = payload or {}
        self.record_analytics_event(
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
        return self.get_analytics_event_counts(hours=hours)

    def get_recent_events(
        self,
        *,
        hours: int = 24,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return self.get_analytics_recent_events(hours=hours, limit=limit)

    def _insert_event_row(
        self,
        event_type: str,
        user_id: int | None = None,
        guild_id: int | None = None,
        game_id: int | None = None,
        match_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if user_id:
            q = """
            INSERT INTO users (user_id, username, is_bot)
            VALUES (%s, 'Unknown', FALSE)
            ON CONFLICT (user_id) DO NOTHING;
            """
            self.database.execute_query(q, (user_id,))
        if guild_id:
            gq = """
            INSERT INTO guilds (guild_id, settings)
            VALUES (%s, '{}'::jsonb)
            ON CONFLICT (guild_id) DO NOTHING;
            """
            self.database.execute_query(gq, (guild_id,))

        metadata_json = json.dumps(metadata) if metadata else None
        query = """
            INSERT INTO analytics_events
                (event_type, user_id, guild_id, game_id, match_id, metadata)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb);
        """
        self.database.execute_query(
            query,
            (event_type, user_id, guild_id, game_id, match_id, metadata_json),
        )

    def record_analytics_event(
        self,
        event_type: str,
        user_id: int | None = None,
        guild_id: int | None = None,
        game_type: str | None = None,
        match_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        resolved_game_id: int | None = None
        if game_type:
            game = self.games.get_game(game_type)
            if game:
                resolved_game_id = game.game_id
        self._insert_event_row(
            event_type,
            user_id,
            guild_id,
            resolved_game_id,
            match_id,
            metadata,
        )

    def get_analytics_event_counts(self, hours: int = 24) -> list[dict[str, Any]]:
        query = """
            SELECT event_type, COUNT(*)::BIGINT AS cnt
            FROM analytics_events
            WHERE created_at > NOW() - (%s * INTERVAL '1 hour')
            GROUP BY event_type
            ORDER BY cnt DESC;
        """
        rows = self.database.execute_query(query, (hours,), fetchall=True)
        return rows or []

    def get_analytics_recent_events(
        self,
        hours: int = 24,
        limit: int = 60,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT event_id, event_type, created_at, user_id, guild_id, game_id, match_id, metadata
            FROM analytics_events
            WHERE created_at > NOW() - (%s * INTERVAL '1 hour')
            ORDER BY created_at DESC
            LIMIT %s;
        """
        rows = self.database.execute_query(query, (hours, limit), fetchall=True)
        return rows or []

    def cleanup_old_analytics(self, days: int | None = None) -> int:
        if days is None:
            days = get_settings().analytics_retention_days
        query = """
            DELETE FROM analytics_events
            WHERE created_at < NOW() - (%s * INTERVAL '1 day');
        """
        with self.database.get_connection() as conn, conn.cursor() as cur:
            cur.execute(query, (days,))
            count = cur.rowcount
            conn.commit()
            return int(count) if count is not None else 0
