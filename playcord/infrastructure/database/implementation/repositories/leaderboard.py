"""Leaderboard and ranking SQL."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playcord.infrastructure.database.implementation.database import Database


@dataclass(slots=True)
class LeaderboardRepository:
    """Guild and global leaderboards, ranks, and ranked player counts."""

    database: Database

    def get_leaderboard(
        self,
        member_user_ids: list[int],
        game_id: int,
        limit: int = 10,
        offset: int = 0,
        min_matches: int = 5,
    ) -> list[dict[str, Any]]:
        """Guild/server leaderboard: same global ratings, filtered to guild members."""
        if not member_user_ids:
            return []
        query = """
            SELECT
                ugr.user_id,
                u.username,
                ugr.mu,
                ugr.sigma,
                calculate_conservative_rating(ugr.mu, ugr.sigma) as conservative_rating,
                ugr.matches_played
            FROM user_game_ratings ugr
            JOIN users u ON ugr.user_id = u.user_id
            WHERE ugr.game_id = %s
              AND ugr.user_id = ANY(%s::bigint[])
              AND ugr.matches_played >= %s
              AND ugr.is_deleted = FALSE
            ORDER BY conservative_rating DESC
            LIMIT %s OFFSET %s;
        """
        results = self.database.execute_query(
            query,
            (game_id, member_user_ids, min_matches, limit, offset),
            fetchall=True,
        )
        return results or []

    def get_global_leaderboard(
        self,
        game_id: int,
        limit: int = 10,
        offset: int = 0,
        min_matches: int = 10,
    ) -> list[dict[str, Any]]:
        """Global leaderboard (all users with a rating row for this game)."""
        query = """
            SELECT
                ugr.user_id,
                u.username,
                ugr.mu,
                ugr.sigma,
                calculate_conservative_rating(ugr.mu, ugr.sigma) as conservative_rating,
                ugr.matches_played
            FROM user_game_ratings ugr
            JOIN users u ON ugr.user_id = u.user_id
            WHERE ugr.game_id = %s
              AND ugr.matches_played >= %s
              AND ugr.is_deleted = FALSE
            ORDER BY conservative_rating DESC
            LIMIT %s OFFSET %s;
        """
        results = self.database.execute_query(
            query,
            (game_id, min_matches, limit, offset),
            fetchall=True,
        )
        return results or []

    def get_user_rank(
        self,
        user_id: int,
        member_user_ids: list[int],
        game_id: int,
        min_matches: int = 5,
    ) -> int:
        """Rank among guild members for this game (1-based), or -1 if unranked."""
        if not member_user_ids:
            return -1
        query = """
            WITH ranked AS (
                SELECT
                    user_id,
                    ROW_NUMBER() OVER (ORDER BY calculate_conservative_rating(mu, sigma) DESC) as rank
                FROM user_game_ratings
                WHERE game_id = %s
                  AND user_id = ANY(%s::bigint[])
                  AND matches_played >= %s
                  AND is_deleted = FALSE
            )
            SELECT rank FROM ranked WHERE user_id = %s;
        """
        result = self.database.execute_query(
            query,
            (game_id, member_user_ids, min_matches, user_id),
            fetchone=True,
        )
        return result["rank"] if result else -1

    def get_user_global_rank(
        self,
        user_id: int,
        game_id: int,
        min_matches: int = 5,
    ) -> int | None:
        query = """
            WITH ranked AS (
                SELECT
                    user_id,
                    ROW_NUMBER() OVER (ORDER BY calculate_conservative_rating(mu, sigma) DESC) as rank
                FROM user_game_ratings
                WHERE game_id = %s
                  AND matches_played >= %s
            )
            SELECT rank FROM ranked WHERE user_id = %s;
        """
        result = self.database.execute_query(
            query,
            (game_id, min_matches, user_id),
            fetchone=True,
        )
        return result["rank"] if result else None

    def get_global_player_count(self, game_id: int, min_matches: int = 5) -> int:
        query = """
            SELECT COUNT(*) as count
            FROM user_game_ratings
            WHERE game_id = %s
              AND matches_played >= %s
              AND is_deleted = FALSE;
        """
        result = self.database.execute_query(
            query,
            (game_id, min_matches),
            fetchone=True,
        )
        return result["count"] if result else 0
