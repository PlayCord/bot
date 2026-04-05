"""
Apply versioned database migrations tracked in database_migrations.
Each migration is a list of SQL statements executed in one transaction.
"""

import logging
import re
from typing import List, Tuple

logger = logging.getLogger("playcord.database.migrations")

# (version, description, statements) — version must match database_migrations.chk_version_format
# Migrations start at 2.4.0 (global per-game ratings). 2.5.0 adds leaderboard index and SQL decay fix.
MIGRATIONS: List[Tuple[str, str, List[str]]] = [
    (
        "2.4.0",
        "Global per-game ratings; remove guild_id from user_game_ratings; drop global_ratings",
        [
            "DROP VIEW IF EXISTS v_active_leaderboard CASCADE",
            "DROP VIEW IF EXISTS v_player_stats CASCADE",
            "DROP VIEW IF EXISTS v_global_leaderboard CASCADE",
            "DROP VIEW IF EXISTS v_inactive_players CASCADE",
            "DROP VIEW IF EXISTS v_guild_activity_summary CASCADE",
            "DROP VIEW IF EXISTS v_game_popularity CASCADE",
            "DROP TRIGGER IF EXISTS trg_enforce_min_rating ON user_game_ratings",
            "DROP TRIGGER IF EXISTS tr_ratings_updated_at ON user_game_ratings",
            """
            CREATE TABLE user_game_ratings_new
            (
                rating_id           BIGSERIAL PRIMARY KEY,
                user_id             BIGINT                    NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
                game_id             INTEGER                   NOT NULL REFERENCES games (game_id) ON DELETE CASCADE,
                mu                  DOUBLE PRECISION          NOT NULL DEFAULT 1000.0,
                sigma               DOUBLE PRECISION          NOT NULL DEFAULT 333.33,
                matches_played      INTEGER     DEFAULT 0     NOT NULL,
                last_played         TIMESTAMPTZ,
                last_sigma_increase TIMESTAMPTZ,
                created_at          TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                updated_at          TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                CONSTRAINT uq_user_game UNIQUE (user_id, game_id),
                CONSTRAINT chk_rating_floor CHECK (mu >= 0.0 AND sigma >= 0.001),
                CONSTRAINT chk_matches_counts CHECK (matches_played >= 0)
            )
            """,
            """
            INSERT INTO user_game_ratings_new (user_id, game_id, mu, sigma, matches_played, last_played,
                                               last_sigma_increase, created_at, updated_at)
            SELECT user_id,
                   game_id,
                   (array_agg(mu ORDER BY matches_played DESC, last_played DESC NULLS LAST))[1],
                (array_agg(sigma ORDER BY matches_played DESC, last_played DESC NULLS LAST))[1],
                SUM(matches_played)::INTEGER,
                MAX(last_played),
                MAX(last_sigma_increase),
                MIN(created_at),
                MAX(updated_at)
            FROM user_game_ratings
            GROUP BY user_id, game_id
            """,
            "DROP TABLE user_game_ratings CASCADE",
            "ALTER TABLE user_game_ratings_new RENAME TO user_game_ratings",
            "ALTER SEQUENCE IF EXISTS user_game_ratings_new_rating_id_seq RENAME TO user_game_ratings_rating_id_seq",
            """
            CREATE INDEX IF NOT EXISTS idx_rating_leaderboard ON user_game_ratings (
                game_id, (mu - 3 * sigma) DESC
                ) WHERE matches_played >= 5
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_rating_user_activity ON user_game_ratings (
                user_id, game_id, last_played DESC
                )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_rating_inactive ON user_game_ratings (last_played)
                WHERE last_played IS NOT NULL
            """,
            "CREATE INDEX IF NOT EXISTS idx_rating_game ON user_game_ratings (game_id)",
            """
            CREATE TRIGGER tr_ratings_updated_at
                BEFORE UPDATE
                ON user_game_ratings
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column()
            """,
            """
            CREATE TRIGGER trg_enforce_min_rating
                BEFORE INSERT OR
            UPDATE OF mu, sigma
            ON user_game_ratings
                FOR EACH ROW
                EXECUTE FUNCTION enforce_user_game_rating_floors()
            """,
            "DROP TABLE IF EXISTS global_ratings CASCADE",
            "DROP FUNCTION IF EXISTS batch_update_global_ratings(INTEGER) CASCADE",
            "DROP FUNCTION IF EXISTS update_global_rating(BIGINT, INTEGER) CASCADE",
            "DROP FUNCTION IF EXISTS get_user_rank(BIGINT, BIGINT, INTEGER) CASCADE",
            """
            CREATE
            OR REPLACE FUNCTION sync_games_played_counts()
            RETURNS INTEGER AS $$
            DECLARE
            updated INTEGER;
            BEGIN
            UPDATE user_game_ratings ugr
            SET matches_played = COALESCE((SELECT COUNT(*) ::INTEGER
                                           FROM match_participants mp
                                                    JOIN matches m ON mp.match_id = m.match_id
                                           WHERE mp.user_id = ugr.user_id
                                             AND m.game_id = ugr.game_id
                                             AND m.status = 'completed'), 0);
            GET DIAGNOSTICS updated = ROW_COUNT;
            RETURN updated;
            END;
            $$
            LANGUAGE plpgsql
            """,
        ],
    ),
    (
        "2.5.0",
        "Guild leaderboard index; apply_skill_decay aligned with global ratings (no guild_id)",
        [
            """
            CREATE INDEX IF NOT EXISTS idx_rating_game_user ON user_game_ratings (game_id, user_id)
            """,
            """
            DROP FUNCTION IF EXISTS apply_skill_decay(integer, double precision) CASCADE
            """,
            """
            CREATE OR REPLACE FUNCTION apply_skill_decay(
                days_inactive INTEGER DEFAULT 30,
                sigma_increase_factor DOUBLE PRECISION DEFAULT 0.1
            )
            RETURNS TABLE (
                user_id BIGINT,
                game_id INTEGER,
                old_sigma DOUBLE PRECISION,
                new_sigma DOUBLE PRECISION,
                days_since_play INTEGER
            ) AS $f$
            BEGIN
                RETURN QUERY
                UPDATE user_game_ratings ugr
                SET
                    sigma = GREATEST(
                        decay_data.new_sig,
                        COALESCE((g.rating_config->>'min_sigma')::DOUBLE PRECISION, 0.001)
                    ),
                    last_sigma_increase = NOW(),
                    updated_at = NOW()
                FROM (
                    SELECT
                        r.rating_id,
                        r.user_id AS uid,
                        r.game_id AS gid,
                        r.sigma AS old_sig,
                        r.sigma * (1 + sigma_increase_factor) AS new_sig,
                        EXTRACT(EPOCH FROM (NOW() - r.last_played))::INTEGER / 86400 AS days_inactive_calc
                    FROM user_game_ratings r
                    WHERE r.last_played < NOW() - (days_inactive || ' days')::INTERVAL
                      AND (r.last_sigma_increase IS NULL
                           OR r.last_sigma_increase < NOW() - (days_inactive || ' days')::INTERVAL)
                ) decay_data
                JOIN games g ON g.game_id = ugr.game_id
                WHERE ugr.rating_id = decay_data.rating_id
                RETURNING
                    decay_data.uid,
                    decay_data.gid,
                    decay_data.old_sig,
                    ugr.sigma,
                    decay_data.days_inactive_calc;
            END;
            $f$ LANGUAGE plpgsql
            """,
            """
            COMMENT ON FUNCTION apply_skill_decay IS 'Apply skill decay to inactive players by increasing sigma'
            """,
        ],
    ),
    (
        "2.6.0",
        "Public match_code (8-char) for thread titles and replay lookup",
        [
            "ALTER TABLE matches ADD COLUMN IF NOT EXISTS match_code VARCHAR(8)",
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_matches_match_code
            ON matches (match_code)
            WHERE match_code IS NOT NULL
            """,
        ],
    ),
]


def apply_migrations(database) -> None:
    """Run any pending migrations (idempotent per version)."""
    for version, description, statements in MIGRATIONS:
        if not re.match(r"^\d+\.\d+(\.\d+)?$", version):
            logger.warning("Skipping migration with invalid version %r", version)
            continue
        row = database._execute_query(
            "SELECT 1 AS ok FROM database_migrations WHERE version = %s;",
            (version,),
            fetchone=True,
        )
        if row:
            continue
        logger.info("Applying database migration %s", version)
        try:
            with database.transaction() as cur:
                for stmt in statements:
                    cur.execute(stmt.strip())
                cur.execute(
                    """
                    INSERT INTO database_migrations (version, description)
                    VALUES (%s, %s);
                    """,
                    (version, description),
                )
        except Exception:
            logger.exception("Migration %s failed", version)
            raise
        logger.info("Migration %s applied successfully", version)
