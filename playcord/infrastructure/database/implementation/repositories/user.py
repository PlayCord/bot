"""User / player records and internal player view."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from playcord.infrastructure.database.implementation.internal_player import (
    InternalPlayer,
)
from playcord.infrastructure.database.models import User, row_to_user

if TYPE_CHECKING:
    from playcord.infrastructure.database.implementation.database import Database


@dataclass(slots=True)
class PlayerRepository:
    database: Database
    games: Any  # GameRepository

    def get(self, user_id: int) -> User | None:
        return self.get_user(user_id)

    def create_user(
        self,
        user_id: int,
        username: str = "Unknown",
        is_bot: bool = False,
    ) -> None:
        query = """
            INSERT INTO users (user_id, username, is_bot)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                username = EXCLUDED.username,
                is_bot = EXCLUDED.is_bot,
                updated_at = NOW();
        """
        self.database.execute_query(query, (user_id, username, is_bot))

    def get_user(self, user_id: int) -> User | None:
        query = "SELECT * FROM users WHERE user_id = %s AND is_deleted = FALSE;"
        result = self.database.execute_query(query, (user_id,), fetchone=True)
        return row_to_user(result) if result else None

    def get_user_preferences(self, user_id: int) -> dict | None:
        query = "SELECT created_at AS joined_at, preferences FROM users WHERE user_id = %s AND is_deleted = FALSE;"
        return self.database.execute_query(query, (user_id,), fetchone=True)

    def delete_user(self, user_id: int) -> None:
        query = (
            "UPDATE users SET is_deleted = TRUE, updated_at = NOW() WHERE user_id = %s;"
        )
        self.database.execute_query(query, (user_id,))

    def restore_user(self, user_id: int) -> None:
        queries = [
            "UPDATE users SET is_deleted = FALSE, updated_at = NOW() WHERE user_id = %s;",
            "UPDATE match_participants SET is_deleted = FALSE, updated_at = NOW() WHERE user_id = %s;",
            "UPDATE match_moves SET is_deleted = FALSE WHERE user_id = %s;",
        ]
        with self.database.transaction() as cur:
            for query in queries:
                cur.execute(query, (user_id,))

    def reset_user_data(self, user_id: int) -> None:
        self.delete_user(user_id)
        self.create_user(user_id, username="Unknown", is_bot=False)

    def get_player(
        self,
        user_id: int,
        username: str | None = None,
    ) -> InternalPlayer | None:
        preferences = self.get_user_preferences(user_id)
        metadata = (
            preferences["preferences"]
            if preferences and preferences.get("preferences")
            else {}
        )

        return InternalPlayer(
            metadata=metadata,
            user_id=user_id,
            username=username,
        )
