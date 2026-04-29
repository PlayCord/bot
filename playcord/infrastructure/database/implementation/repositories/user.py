"""User / player records and internal player view."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from playcord.infrastructure.database.implementation.database import Database
from playcord.infrastructure.database.implementation.internal_player import (
    InternalPlayer,
)
from playcord.infrastructure.database.models import User, row_to_user


@dataclass(slots=True)
class PlayerRepository:
    database: Database
    games: Any  # GameRepository (avoid typing cycle with string if needed)
    ratings: Any  # RatingRepository

    def get(self, user_id: int) -> User | None:
        return self.get_user(user_id)

    def create_user(
        self, user_id: int, username: str = "Unknown", is_bot: bool = False,
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

    def update_user_preferences(
        self, user_id: int, preferences: dict[str, Any],
    ) -> None:
        preferences_json = json.dumps(preferences)
        query = """
            INSERT INTO users (user_id, username, preferences)
            VALUES (%s, 'Unknown', %s::jsonb)
            ON CONFLICT (user_id) DO UPDATE SET
                preferences = EXCLUDED.preferences,
                updated_at = NOW();
        """
        self.database.execute_query(query, (user_id, preferences_json))

    def get_user_preferences(self, user_id: int) -> dict | None:
        query = "SELECT created_at AS joined_at, preferences FROM users WHERE user_id = %s AND is_deleted = FALSE;"
        result = self.database.execute_query(query, (user_id,), fetchone=True)
        if result and result["preferences"]:
            return result
        return result

    def delete_user(self, user_id: int) -> None:
        query = (
            "UPDATE users SET is_deleted = TRUE, updated_at = NOW() WHERE user_id = %s;"
        )
        self.database.execute_query(query, (user_id,))

    def restore_user(self, user_id: int) -> None:
        queries = [
            "UPDATE users SET is_deleted = FALSE, updated_at = NOW() WHERE user_id = %s;",
            "UPDATE user_game_ratings SET is_deleted = FALSE, updated_at = NOW() WHERE user_id = %s;",
            "UPDATE match_participants SET is_deleted = FALSE, updated_at = NOW() WHERE user_id = %s;",
            "UPDATE match_moves SET is_deleted = FALSE WHERE user_id = %s;",
            "UPDATE rating_history SET is_deleted = FALSE WHERE user_id = %s;",
        ]
        with self.database.transaction() as cur:
            for query in queries:
                cur.execute(query, (user_id,))

    def archive_user(self, user_id: int) -> dict[str, int]:
        counts: dict[str, int] = {}
        queries: list[tuple[str, str]] = [
            (
                "users",
                "SELECT COUNT(*) FROM users WHERE user_id = %s AND is_deleted = TRUE;",
            ),
            (
                "user_game_ratings",
                "SELECT COUNT(*) FROM user_game_ratings WHERE user_id = %s;",
            ),
            (
                "match_participants",
                "SELECT COUNT(*) FROM match_participants WHERE user_id = %s;",
            ),
            ("match_moves", "SELECT COUNT(*) FROM match_moves WHERE user_id = %s;"),
            (
                "rating_history",
                "SELECT COUNT(*) FROM rating_history WHERE user_id = %s;",
            ),
        ]
        for table_name, query in queries:
            result = self.database.execute_query(query, (user_id,), fetchone=True)
            counts[table_name] = result["count"] if result else 0
        return counts

    def search_users(self, query_text: str, limit: int = 10) -> list[User]:
        query = """
            SELECT * FROM users
            WHERE username ILIKE %s AND is_active = TRUE AND is_deleted = FALSE
            LIMIT %s;
        """
        pattern = f"%{query_text}%"
        results = self.database.execute_query(query, (pattern, limit), fetchall=True)
        return [row_to_user(row) for row in results] if results else []

    def upsert(self, user_id: int, username: str, *, is_bot: bool = False) -> None:
        self.create_user(user_id, username, is_bot)

    def reset_user_data(self, user_id: int) -> None:
        self.delete_user(user_id)
        self.create_user(user_id, username="Unknown", is_bot=False)

    def get_user_all_ratings(self, user_id: int) -> list[Any]:
        return self.ratings.get_user_all_ratings(user_id)

    def get_user_global_rank(
        self, user_id: int, game_id: int, min_matches: int = 5,
    ) -> int | None:
        return self.ratings.get_user_global_rank(
            user_id, game_id, min_matches=min_matches,
        )

    def get_rating_history(
        self,
        user_id: int,
        guild_id: int | None,
        game_id: int,
        *,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        return self.ratings.get_rating_history(user_id, guild_id, game_id, days=days)

    def get_player(
        self, user_id: int, username: str | None = None,
    ) -> InternalPlayer | None:
        preferences = self.get_user_preferences(user_id)
        metadata = (
            preferences["preferences"]
            if preferences and preferences.get("preferences")
            else {}
        )

        all_ratings = self.get_user_all_ratings(user_id)
        ratings: dict[str, dict[str, float]] = {}
        for rating in all_ratings:
            game = self.games.get_by_id(rating.game_id)
            if game:
                ratings[game.game_name] = {"mu": rating.mu, "sigma": rating.sigma}

        return InternalPlayer(
            ratings=ratings,
            metadata=metadata,
            id=user_id,
            username=username,
        )

    @staticmethod
    def to_domain(player: Any) -> Any:
        from playcord.core.player import Player  # noqa: PLC0415

        return Player.from_legacy(player)

    def get_user_game_ratings(
        self,
        user_id: int,
        game_name_or_id: int | str,
        guild_id: int | None = None,  # noqa: ARG002
    ) -> dict[str, Any] | None:
        if isinstance(game_name_or_id, str):
            game = self.games.get_game(game_name_or_id)
            if not game:
                return None
            game_id = game.game_id
        else:
            game_id = game_name_or_id

        rating = self.ratings.get_user_rating(user_id, game_id)
        if not rating:
            return None

        return {
            "mu": rating.mu,
            "sigma": rating.sigma,
            "matches_played": rating.matches_played,
            "last_played": rating.last_played,
        }

    def initialize_user_game_ratings(
        self,
        user_id: int,
        game_name: str,
        guild_id: int | None = None,  # noqa: ARG002
    ) -> None:
        game = self.games.get_game(game_name)
        if not game:
            raise ValueError(f"Game {game_name} not found")
        self.ratings.initialize_user_rating(user_id, game.game_id)

    def update_ratings_after_match(
        self,
        user_id: int,
        game_name: str,
        mu: float,
        sigma: float,
        matches_played_increment: int = 1,
        guild_id: int | None = None,  # noqa: ARG002
    ) -> None:
        game = self.games.get_game(game_name)
        if not game:
            raise ValueError(f"Game {game_name} not found")
        self.ratings.update_rating(
            user_id, game.game_id, mu, sigma, matches_increment=matches_played_increment,
        )

    def reset_user_game_ratings(
        self,
        user_id: int,
        game_name: str,
        guild_id: int | None = None,  # noqa: ARG002
    ) -> None:
        game = self.games.get_game(game_name)
        if not game:
            raise ValueError(f"Game {game_name} not found")
        self.ratings.reset_user_rating(user_id, game.game_id)

    def delete_user_game_ratings(
        self,
        user_id: int,
        game_name: str,
        guild_id: int | None = None,  # noqa: ARG002
    ) -> None:
        game = self.games.get_game(game_name)
        if not game:
            raise ValueError(f"Game {game_name} not found")
        self.ratings.delete_user_rating(user_id, game.game_id)

    def get_preferences(self, user_id: int) -> dict[str, Any] | None:
        return self.get_user_preferences(user_id)

    def update_preferences(self, user_id: int, preferences: dict[str, Any]) -> None:
        self.update_user_preferences(user_id, preferences)
