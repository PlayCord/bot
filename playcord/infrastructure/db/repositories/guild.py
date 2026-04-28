"""Guild settings and maintenance operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playcord.infrastructure.db.database import Database


@dataclass(slots=True)
class GuildRepository:
    database: Database

    def merge_settings(self, guild_id: int, patch: dict[str, Any]) -> None:
        self.database.merge_guild_settings(guild_id, patch)

    def get_playcord_channel_id(self, guild_id: int) -> int | None:
        return self.database.get_playcord_channel_id(guild_id)

    def delete_guild(self, guild_id: int) -> None:
        self.database.delete_guild(guild_id)

    def cleanup_old_analytics(self, days: int | None = None) -> int:
        return self.database.cleanup_old_analytics(days=days)

    def reset_all_data(self) -> None:
        self.database.reset_all_data()

    def reset_game_data(self, game_id: int) -> Any:
        return self.database.reset_game_data(game_id)

    def reset_user_data(self, user_id: int) -> None:
        self.database.reset_user_data(user_id)

    def reset_guild_data(self, guild_id: int) -> None:
        self.database.reset_guild_data(guild_id)
