"""Guild (server) settings and admin wiring to other repositories."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from playcord.infrastructure.database.implementation.database import Database
from playcord.infrastructure.database.models import Guild, row_to_guild


@dataclass(slots=True)
class GuildRepository:
    database: Database
    analytics: Any  # AnalyticsRepository
    players: Any  # PlayerRepository
    games: Any  # GameRepository
    maintenance: Any  # MaintenanceRepository

    def create_guild(
        self, guild_id: int, settings: dict[str, Any] | None = None,
    ) -> None:
        settings_json = json.dumps(settings or {})
        query = """
            INSERT INTO guilds (guild_id, settings)
            VALUES (%s, %s::jsonb)
            ON CONFLICT (guild_id) DO UPDATE SET
                is_active = TRUE,
                updated_at = NOW();
        """
        self.database.execute_query(query, (guild_id, settings_json))

    def get_guild(self, guild_id: int) -> Guild | None:
        query = "SELECT * FROM guilds WHERE guild_id = %s;"
        result = self.database.execute_query(query, (guild_id,), fetchone=True)
        return row_to_guild(result) if result else None

    def update_guild_settings(self, guild_id: int, settings: dict[str, Any]) -> None:
        settings_json = json.dumps(settings)
        query = """
            INSERT INTO guilds (guild_id, settings)
            VALUES (%s, %s::jsonb)
            ON CONFLICT (guild_id) DO UPDATE SET
                settings = EXCLUDED.settings,
                updated_at = NOW();
        """
        self.database.execute_query(query, (guild_id, settings_json))

    def get_guild_settings(self, guild_id: int) -> dict | None:
        query = "SELECT settings FROM guilds WHERE guild_id = %s;"
        result = self.database.execute_query(query, (guild_id,), fetchone=True)
        return result["settings"] if result else None

    def merge_guild_settings(self, guild_id: int, patch: dict[str, Any]) -> None:
        self.create_guild(guild_id, {})
        query = """
            UPDATE guilds
            SET settings = COALESCE(settings, '{}'::jsonb) || %s::jsonb,
                updated_at = NOW()
            WHERE guild_id = %s;
        """
        self.database.execute_query(query, (json.dumps(patch), guild_id))

    def merge_settings(self, guild_id: int, patch: dict[str, Any]) -> None:
        self.merge_guild_settings(guild_id, patch)

    def get_playcord_channel_id(self, guild_id: int) -> int | None:
        s = self.get_guild_settings(guild_id)
        if not s:
            return None
        raw = s.get("playcord_channel_id")
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def delete_guild(self, guild_id: int) -> None:
        query = "DELETE FROM guilds WHERE guild_id = %s;"
        self.database.execute_query(query, (guild_id,))

    def get_active_guilds(self) -> list[Guild]:
        query = "SELECT * FROM guilds WHERE is_active = TRUE ORDER BY created_at DESC;"
        results = self.database.execute_query(query, fetchall=True)
        return [row_to_guild(row) for row in results] if results else []

    def reset_guild_data(self, guild_id: int) -> None:
        self.delete_guild(guild_id)
        self.create_guild(guild_id, settings={})

    def cleanup_old_analytics(self, days: int | None = None) -> int:
        return self.analytics.cleanup_old_analytics(days=days)

    def reset_all_data(self) -> None:
        self.maintenance.reset_all_data()

    def reset_game_data(self, game_id: int) -> Any:
        return self.games.reset_game_data(game_id)

    def reset_user_data(self, user_id: int) -> None:
        self.players.reset_user_data(user_id)
