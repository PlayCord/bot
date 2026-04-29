"""Schema-wide maintenance, reporting, and health."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from playcord.infrastructure.database.implementation.core import migrations

if TYPE_CHECKING:
    from playcord.infrastructure.database.implementation.database import Database


@dataclass(slots=True)
class MaintenanceRepository:
    database: Database
    games: Any  # GameRepository

    def reset_all_data(self) -> None:
        self.games.clear_caches()
        with self.database.get_connection() as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("DROP SCHEMA IF EXISTS public CASCADE;")
                cur.execute("CREATE SCHEMA public;")
                cur.execute("DROP TABLE IF EXISTS database_migrations;")
            conn.autocommit = False

        migrations.apply_migrations(self.database)
        self.database.refresh_sql_assets()
        self.games.sync_games_from_code()

    def apply_skill_decay(
        self,
        days_inactive: int = 30,
        sigma_increase: float = 0.1,
    ) -> int:
        query = """
            UPDATE user_game_ratings
            SET sigma = sigma * (1 + %s),
                last_sigma_increase = NOW(),
                updated_at = NOW()
            WHERE last_played < NOW() - (%s * INTERVAL '1 day')
              AND (last_sigma_increase IS NULL
                   OR last_sigma_increase < NOW() - (%s * INTERVAL '1 day'))
            RETURNING user_id;
        """
        with self.database.get_connection() as conn, conn.cursor() as cur:
            cur.execute(query, (sigma_increase, days_inactive, days_inactive))
            results = cur.fetchall()
            conn.commit()
            return len(results) if results else 0

    def get_inactive_users(self, guild_id: int, days: int = 30) -> list[dict[str, Any]]:
        query = """
            SELECT DISTINCT
                ugr.user_id,
                u.username,
                ugr.game_id,
                ugr.last_played,
                EXTRACT(EPOCH FROM (NOW() - ugr.last_played))::INTEGER / 86400 as days_inactive
            FROM user_game_ratings ugr
            JOIN users u ON ugr.user_id = u.user_id
            WHERE ugr.user_id IN (
                SELECT DISTINCT mp.user_id
                FROM match_participants mp
                JOIN matches m ON mp.match_id = m.match_id
                WHERE m.guild_id = %s AND m.status = 'completed' AND mp.is_deleted = FALSE
            )
              AND ugr.last_played < NOW() - (%s * INTERVAL '1 day')
              AND ugr.is_deleted = FALSE
            ORDER BY ugr.last_played ASC;
        """
        results = self.database.execute_query(query, (guild_id, days), fetchall=True)
        return results or []

    def archive_old_matches(self, days: int = 365) -> int:
        metadata_update = json.dumps(True)
        query = """
            UPDATE matches
            SET metadata = jsonb_set(
                COALESCE(metadata, '{}'::jsonb),
                '{archived}',
                %s::jsonb
            )
            WHERE ended_at < NOW() - (%s * INTERVAL '1 day')
              AND status = 'completed'
              AND NOT (metadata ? 'archived' AND (metadata->>'archived')::boolean = true)
            RETURNING match_id;
        """
        with self.database.get_connection() as conn, conn.cursor() as cur:
            cur.execute(query, (metadata_update, days))
            results = cur.fetchall()
            conn.commit()
            return len(results) if results else 0

    def vacuum_analyze(self) -> None:
        with self.database.get_connection() as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("VACUUM ANALYZE;")
            conn.autocommit = False

    def get_match_count_by_game(self, guild_id: int, days: int = 30) -> dict[str, int]:
        query = """
            SELECT
                g.display_name as game_name,
                COUNT(*) as match_count
            FROM matches m
            JOIN games g ON m.game_id = g.game_id
            WHERE m.guild_id = %s
              AND m.ended_at > NOW() - (%s * INTERVAL '1 day')
              AND m.status = 'completed'
            GROUP BY g.display_name
            ORDER BY match_count DESC;
        """
        results = self.database.execute_query(query, (guild_id, days), fetchall=True)
        return (
            {row["game_name"]: row["match_count"] for row in results} if results else {}
        )

    def get_player_retention(self, guild_id: int, days: int = 7) -> float:
        query = """
            WITH guild_users AS (
                SELECT DISTINCT mp.user_id
                FROM match_participants mp
                JOIN matches m ON mp.match_id = m.match_id
                WHERE m.guild_id = %s AND m.status = 'completed' AND mp.is_deleted = FALSE
            ),
            active_players AS (
                SELECT COUNT(DISTINCT mp.user_id) as count
                FROM match_participants mp
                JOIN matches m ON mp.match_id = m.match_id
                WHERE m.guild_id = %s
                  AND m.status = 'completed'
                  AND m.ended_at > NOW() - (%s * INTERVAL '1 day')
                  AND mp.is_deleted = FALSE
            ),
            total_players AS (
                SELECT COUNT(*)::BIGINT as count FROM guild_users
            )
            SELECT
                CASE
                    WHEN total_players.count > 0
                    THEN (active_players.count::FLOAT / total_players.count::FLOAT) * 100.0
                    ELSE 0.0
                END as retention_rate
            FROM active_players, total_players;
        """
        result = self.database.execute_query(
            query,
            (guild_id, guild_id, days),
            fetchone=True,
        )
        return result["retention_rate"] if result else 0.0

    def get_most_active_players(
        self,
        guild_id: int,
        game_id: int,
        days: int = 7,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT
                u.user_id,
                u.username,
                COUNT(DISTINCT m.match_id) as match_count
            FROM match_participants mp
            JOIN matches m ON mp.match_id = m.match_id
            JOIN users u ON mp.user_id = u.user_id
            WHERE m.guild_id = %s
              AND m.game_id = %s
              AND m.ended_at > NOW() - (%s * INTERVAL '1 day')
              AND m.status = 'completed'
              AND mp.is_deleted = FALSE
            GROUP BY u.user_id, u.username
            ORDER BY match_count DESC
            LIMIT %s;
        """
        results = self.database.execute_query(
            query,
            (guild_id, game_id, days, limit),
            fetchall=True,
        )
        return results or []

    def count_matches(
        self,
        guild_id: int,
        game_id: int,
        is_rated: bool | None = None,
    ) -> int:
        if is_rated is not None:
            query = """
                SELECT COUNT(*) as count FROM matches
                WHERE guild_id = %s AND game_id = %s AND is_rated = %s;
            """
            result = self.database.execute_query(
                query,
                (guild_id, game_id, is_rated),
                fetchone=True,
            )
        else:
            query = """
                SELECT COUNT(*) as count FROM matches
                WHERE guild_id = %s AND game_id = %s;
            """
            result = self.database.execute_query(
                query,
                (guild_id, game_id),
                fetchone=True,
            )
        return result["count"] if result else 0

    def count_users(self, guild_id: int | None = None, is_active: bool = True) -> int:
        if guild_id is not None:
            query = """
                SELECT COUNT(DISTINCT mp.user_id) as count
                FROM match_participants mp
                JOIN matches m ON mp.match_id = m.match_id
                WHERE m.guild_id = %s AND m.status = 'completed';
            """
            result = self.database.execute_query(query, (guild_id,), fetchone=True)
        else:
            query = """
                SELECT COUNT(*) as count FROM users
                WHERE is_active = %s;
            """
            result = self.database.execute_query(query, (is_active,), fetchone=True)
        return result["count"] if result else 0

    def get_database_stats(self) -> dict[str, Any]:
        queries = {
            "total_users": "SELECT COUNT(*) as count FROM users WHERE is_active = TRUE",
            "total_guilds": "SELECT COUNT(*) as count FROM guilds WHERE is_active = TRUE",
            "total_games": "SELECT COUNT(*) as count FROM games WHERE is_active = TRUE",
            "total_matches": "SELECT COUNT(*) as count FROM matches",
            "active_matches": "SELECT COUNT(*) as count FROM matches WHERE status = 'in_progress'",
            "total_moves": "SELECT COUNT(*) as count FROM match_moves WHERE is_deleted = FALSE",
            "total_ratings": "SELECT COUNT(*) as count FROM user_game_ratings WHERE is_deleted = FALSE",
        }
        stats: dict[str, Any] = {}
        for key, query in queries.items():
            result = self.database.execute_query(query, fetchone=True)
            stats[key] = result["count"] if result else 0
        return stats

    def health_check(self) -> bool:
        from playcord.infrastructure.logging import get_logger  # noqa: PLC0415

        log = get_logger("database")
        try:
            result = self.database.execute_query("SELECT 1 as check;", fetchone=True)
            return result is not None and result["check"] == 1
        except Exception as e:
            log.exception("Health check failed: %s", e)
            return False
