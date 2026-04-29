"""Per-game user ratings and rating history queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playcord.infrastructure.config import get_settings
from playcord.infrastructure.database.implementation.database import Database
from playcord.infrastructure.database.implementation.repositories.game import (
    GameRepository,
)
from playcord.infrastructure.database.implementation.repositories.leaderboard import (
    LeaderboardRepository,
)
from playcord.infrastructure.database.models import Rating, row_to_rating


@dataclass(slots=True)
class RatingRepository:
    database: Database
    games: GameRepository
    leaderboard: LeaderboardRepository

    def clamp_rating(
        self, mu: float, sigma: float, game_id: int,
    ) -> tuple[float, float]:
        """Clamp mu/sigma using global config and per-game rating_config floors."""
        cfg = get_settings().ratings
        min_mu = float(cfg.min_mu)
        min_sigma = float(cfg.min_sigma)
        game = self.games.get_by_id(game_id)
        if game and game.rating_config:
            min_mu = float(game.rating_config.get("min_mu", min_mu))
            min_sigma = max(
                min_sigma,
                float(game.rating_config.get("min_sigma", min_sigma)),
            )
        min_sigma = max(min_sigma, 0.001)
        min_mu = max(min_mu, 0.0)
        return max(mu, min_mu), max(sigma, min_sigma)

    def initialize_user_rating(self, user_id: int, game_id: int) -> None:
        game = self.games.get_by_id(game_id)
        if not game:
            raise ValueError(f"Game {game_id} not found")

        mu = game.default_mu
        sigma = game.default_sigma

        query = """
            INSERT INTO user_game_ratings (user_id, game_id, mu, sigma)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, game_id) DO NOTHING;
        """
        self.database.execute_query(query, (user_id, game_id, mu, sigma))

    def get_user_rating(self, user_id: int, game_id: int) -> Rating | None:
        query = """
            SELECT * FROM user_game_ratings
            WHERE user_id = %s AND game_id = %s AND is_deleted = FALSE;
        """
        result = self.database.execute_query(query, (user_id, game_id), fetchone=True)
        return row_to_rating(result) if result else None

    def get_user_all_ratings(self, user_id: int) -> list[Rating]:
        query = """
            SELECT * FROM user_game_ratings
            WHERE user_id = %s AND is_deleted = FALSE
            ORDER BY game_id;
        """
        results = self.database.execute_query(query, (user_id,), fetchall=True)
        return [row_to_rating(row) for row in results] if results else []

    def update_rating(
        self,
        user_id: int,
        game_id: int,
        mu: float,
        sigma: float,
        matches_increment: int = 1,
    ) -> None:
        mu, sigma = self.clamp_rating(mu, sigma, game_id)
        query = """
            UPDATE user_game_ratings
            SET mu = %s,
                sigma = %s,
                matches_played = matches_played + %s,
                last_played = NOW(),
                updated_at = NOW()
            WHERE user_id = %s AND game_id = %s;
        """
        self.database.execute_query(
            query, (mu, sigma, matches_increment, user_id, game_id),
        )

    def bulk_update_ratings(self, updates: list[dict[str, Any]]) -> None:
        with self.database.transaction() as cur:
            for update in updates:
                matches_increment = int(update.get("matches_increment", 1))
                query = """
                    UPDATE user_game_ratings
                    SET mu = %s, sigma = %s, matches_played = matches_played + %s,
                        last_played = NOW(), updated_at = NOW()
                    WHERE user_id = %s AND game_id = %s;
                """
                mu_c, sig_c = self.clamp_rating(
                    update["mu"], update["sigma"], update["game_id"],
                )
                cur.execute(
                    query,
                    (
                        mu_c,
                        sig_c,
                        matches_increment,
                        update["user_id"],
                        update["game_id"],
                    ),
                )

    def reset_user_rating(self, user_id: int, game_id: int) -> None:
        game = self.games.get_by_id(game_id)
        if not game:
            raise ValueError(f"Game {game_id} not found")

        query = """
            UPDATE user_game_ratings
            SET mu = %s,
                sigma = %s,
                matches_played = 0,
                last_played = NULL,
                last_sigma_increase = NULL,
                updated_at = NOW()
            WHERE user_id = %s AND game_id = %s;
        """
        self.database.execute_query(
            query, (game.default_mu, game.default_sigma, user_id, game_id),
        )

    def delete_user_rating(self, user_id: int, game_id: int) -> None:
        query = """
            DELETE FROM user_game_ratings
            WHERE user_id = %s AND game_id = %s;
        """
        self.database.execute_query(query, (user_id, game_id))

    def get_rating_history(
        self,
        user_id: int,
        guild_id: int | None,
        game_id: int,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT
                history_id,
                match_id,
                mu_before,
                sigma_before,
                mu_after,
                sigma_after,
                (mu_after - mu_before) as mu_delta,
                (sigma_after - sigma_before) as sigma_delta,
                created_at
            FROM rating_history
            WHERE user_id = %s
              AND game_id = %s
              AND is_deleted = FALSE
              AND created_at > NOW() - (%s * INTERVAL '1 day')
        """
        params: list[Any] = [user_id, game_id, days]
        if guild_id is not None:
            query += " AND guild_id = %s"
            params.append(guild_id)
        query += """
            ORDER BY created_at DESC;
        """
        results = self.database.execute_query(query, tuple(params), fetchall=True)
        return results or []

    def get_user_global_rank(
        self, user_id: int, game_id: int, min_matches: int = 5,
    ) -> int | None:
        return self.leaderboard.get_user_global_rank(
            user_id, game_id, min_matches=min_matches,
        )

    def calculate_global_ratings(self, game_id: int) -> int:
        """No-op count: ratings are stored only in user_game_ratings."""
        return 0
