"""Player-related repository methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playcord.domain.player import Player

from playcord.utils.database import Database


@dataclass(slots=True)
class PlayerRepository:
    database: Database

    def get(self, user_id: int) -> Any | None:
        return self.database.get_user(user_id)

    def upsert(self, user_id: int, username: str, *, is_bot: bool = False) -> None:
        self.database.upsert_user(user_id, username, is_bot)

    def get_preferences(self, user_id: int) -> dict[str, Any] | None:
        return self.database.get_user_preferences(user_id)

    def update_preferences(self, user_id: int, preferences: dict[str, Any]) -> None:
        self.database.update_user_preferences(user_id, preferences)

    @staticmethod
    def to_domain(player: Any) -> Player:
        return Player.from_legacy(player)
