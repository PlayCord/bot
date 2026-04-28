"""Player-related repository methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playcord.domain.player import Player
from playcord.infrastructure.db.database import Database


@dataclass(slots=True)
class PlayerRepository:
    database: Database

    def get(self, user_id: int) -> Any | None:
        return self.database.get_user(user_id)

    def upsert(self, user_id: int, username: str, *, is_bot: bool = False) -> None:
        self.database.create_user(user_id, username, is_bot)

    def get_discord_player(self, user: Any, guild_id: int) -> Any | None:
        return self.database.get_player(user, guild_id)

    def get_user_all_ratings(self, user_id: int) -> list[Any]:
        return self.database.get_user_all_ratings(user_id)

    def get_user_global_rank(self, user_id: int, game_id: int) -> int | None:
        return self.database.get_user_global_rank(user_id, game_id)

    def get_rating_history(
        self,
        user_id: int,
        guild_id: int | None,
        game_id: int,
        *,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        return self.database.get_rating_history(user_id, guild_id, game_id, days=days)

    def get_preferences(self, user_id: int) -> dict[str, Any] | None:
        return self.database.get_user_preferences(user_id)

    def update_preferences(self, user_id: int, preferences: dict[str, Any]) -> None:
        self.database.update_user_preferences(user_id, preferences)

    @staticmethod
    def to_domain(player: Any) -> Player:
        return Player.from_legacy(player)
