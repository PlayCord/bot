"""
Apply versioned database migrations tracked in database_migrations.
Each migration is a list of SQL statements executed in one transaction.
"""

import hashlib
import re
from typing import List, Tuple

from utils.logging_config import get_logger

logger = get_logger("database.migrations")

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
            CREATE
            OR REPLACE FUNCTION apply_skill_decay(
                days_inactive INTEGER DEFAULT 30,
                sigma_increase_factor DOUBLE PRECISION DEFAULT 0.1
            )
            RETURNS TABLE (
                user_id BIGINT,
                game_id INTEGER,
                old_sigma DOUBLE PRECISION,
                new_sigma DOUBLE PRECISION,
                days_since_play INTEGER
            ) AS
            $f$
            BEGIN
            RETURN QUERY
            UPDATE user_game_ratings ugr
            SET sigma               = GREATEST(
                    decay_data.new_sig,
                    COALESCE((g.rating_config ->>'min_sigma') ::DOUBLE PRECISION, 0.001)
                                      ),
                last_sigma_increase = NOW(),
                updated_at          = NOW() FROM (
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
                JOIN games g
            ON g.game_id = ugr.game_id
            WHERE ugr.rating_id = decay_data.rating_id
                RETURNING
                decay_data.uid
                , decay_data.gid
                , decay_data.old_sig
                , ugr.sigma
                , decay_data.days_inactive_calc;
            END;
            $f$
            LANGUAGE plpgsql
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
    (
        "2.7.0",
        "Replay events table, normalized timestamps, rating-history retention, and schema cleanup",
        [
            "DROP VIEW IF EXISTS v_active_leaderboard CASCADE",
            "DROP VIEW IF EXISTS v_match_outcomes CASCADE",
            "DROP VIEW IF EXISTS v_player_stats CASCADE",
            "DROP VIEW IF EXISTS v_global_leaderboard CASCADE",
            "DROP VIEW IF EXISTS v_recent_activity CASCADE",
            "DROP VIEW IF EXISTS v_match_summary CASCADE",
            "DROP VIEW IF EXISTS v_user_match_history CASCADE",
            "DROP VIEW IF EXISTS v_inactive_players CASCADE",
            "DROP VIEW IF EXISTS v_guild_activity_summary CASCADE",
            "DROP VIEW IF EXISTS v_game_popularity CASCADE",
            "DROP TRIGGER IF EXISTS tr_matches_updated_at ON matches",
            "DROP TRIGGER IF EXISTS tr_match_participants_updated_at ON match_participants",
            "DROP TRIGGER IF EXISTS trg_matches_completed_counts ON matches",
            "DROP FUNCTION IF EXISTS get_match_replay_data(BIGINT) CASCADE",
            "DROP FUNCTION IF EXISTS prevent_direct_rating_updates() CASCADE",
            "DROP TABLE IF EXISTS game_seasons CASCADE",
            "ALTER TABLE guilds DROP COLUMN IF EXISTS joined_at",
            "DROP INDEX IF EXISTS idx_guilds_active",
            "CREATE INDEX IF NOT EXISTS idx_guilds_active ON guilds (is_active, created_at DESC)",
            "ALTER TABLE users DROP COLUMN IF EXISTS joined_at",
            "DROP INDEX IF EXISTS idx_users_active",
            "CREATE INDEX IF NOT EXISTS idx_users_active ON users (is_active, created_at DESC)",
            "ALTER TABLE matches ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE match_participants ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
            """
            CREATE TRIGGER tr_matches_updated_at
                BEFORE UPDATE
                ON matches
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column()
            """,
            """
            CREATE TRIGGER tr_match_participants_updated_at
                BEFORE UPDATE
                ON match_participants
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column()
            """,
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'moves' AND column_name = 'timestamp'
                ) THEN
                    ALTER TABLE moves RENAME COLUMN timestamp TO created_at;
                END IF;
            END$$
            """,
            "DROP INDEX IF EXISTS idx_moves_user",
            "DROP INDEX IF EXISTS idx_moves_timestamp",
            "DROP INDEX IF EXISTS idx_moves_created_at",
            "CREATE INDEX IF NOT EXISTS idx_moves_user ON moves (user_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_moves_created_at ON moves (created_at DESC)",
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'analytics_events' AND column_name = 'timestamp'
                ) THEN
                    ALTER TABLE analytics_events RENAME COLUMN timestamp TO created_at;
                END IF;
            END$$
            """,
            "DROP INDEX IF EXISTS idx_analytics_type_time",
            "DROP INDEX IF EXISTS idx_analytics_user",
            "DROP INDEX IF EXISTS idx_analytics_guild",
            "DROP INDEX IF EXISTS idx_analytics_timestamp",
            "DROP INDEX IF EXISTS idx_analytics_created_at",
            "CREATE INDEX IF NOT EXISTS idx_analytics_type_time ON analytics_events (event_type, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_analytics_user ON analytics_events (user_id, created_at DESC) WHERE user_id IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS idx_analytics_guild ON analytics_events (guild_id, created_at DESC) WHERE guild_id IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS idx_analytics_created_at ON analytics_events (created_at DESC)",
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'rating_history' AND column_name = 'timestamp'
                ) THEN
                    ALTER TABLE rating_history RENAME COLUMN timestamp TO created_at;
                END IF;
            END$$
            """,
            "ALTER TABLE rating_history ALTER COLUMN guild_id DROP NOT NULL",
            "ALTER TABLE rating_history DROP CONSTRAINT IF EXISTS fk_history_guild",
            "ALTER TABLE rating_history ADD CONSTRAINT fk_history_guild FOREIGN KEY (guild_id) REFERENCES guilds (guild_id) ON DELETE SET NULL",
            "DROP INDEX IF EXISTS idx_history_user_game",
            "DROP INDEX IF EXISTS idx_history_guild_game",
            "CREATE INDEX IF NOT EXISTS idx_history_user_game ON rating_history (user_id, game_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_history_guild_game ON rating_history (guild_id, game_id, created_at DESC)",
            """
            CREATE TABLE IF NOT EXISTS replay_events
            (
                event_id
                BIGSERIAL
                PRIMARY
                KEY,
                match_id
                BIGINT
                NOT
                NULL
                REFERENCES
                matches
            (
                match_id
            ) ON DELETE CASCADE,
                sequence_number INTEGER NOT NULL,
                event_type VARCHAR
            (
                100
            ) NOT NULL,
                actor_user_id BIGINT REFERENCES users
            (
                user_id
            )
              ON DELETE SET NULL,
                payload JSONB DEFAULT '{}'::jsonb NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW
            (
            ) NOT NULL,
                CONSTRAINT uq_replay_sequence UNIQUE
            (
                match_id,
                sequence_number
            ),
                CONSTRAINT chk_replay_sequence CHECK
            (
                sequence_number
                >=
                1
            )
                )
            """,
            "CREATE INDEX IF NOT EXISTS idx_replay_match_sequence ON replay_events (match_id, sequence_number ASC)",
            "CREATE INDEX IF NOT EXISTS idx_replay_actor ON replay_events (actor_user_id, created_at DESC) WHERE actor_user_id IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS idx_replay_type ON replay_events (event_type, created_at DESC)",
            """
            DO $$
            DECLARE
                m RECORD;
                raw_line TEXT;
                seq INTEGER;
                evt JSONB;
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'matches' AND column_name = 'replay_log'
                ) THEN
                    FOR m IN
                        SELECT match_id, COALESCE(replay_log, '') AS replay_log, created_at
                        FROM matches
                    LOOP
                        seq := 0;
                        FOREACH raw_line IN ARRAY string_to_array(m.replay_log, E'\\n')
                        LOOP
                            raw_line := btrim(raw_line);
                            IF raw_line = '' THEN
                                CONTINUE;
                            END IF;
                            BEGIN
                                evt := raw_line::jsonb;
                            EXCEPTION WHEN others THEN
                                CONTINUE;
                            END;
                            seq := seq + 1;
                            INSERT INTO replay_events (
                                match_id,
                                sequence_number,
                                event_type,
                                actor_user_id,
                                payload,
                                created_at
                            )
                            VALUES (
                                m.match_id,
                                seq,
                                COALESCE(evt->>'type', 'event'),
                                CASE
                                    WHEN jsonb_typeof(evt->'user_id') = 'number' THEN (evt->>'user_id')::BIGINT
                                    ELSE NULL
                                END,
                                evt - 'type' - 'user_id',
                                m.created_at
                            )
                            ON CONFLICT (match_id, sequence_number) DO NOTHING;
                        END LOOP;
                    END LOOP;
                END IF;
            END$$
            """,
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'matches' AND column_name = 'replay_log'
                ) THEN
                    ALTER TABLE matches DROP COLUMN replay_log;
                END IF;
            END$$
            """,
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_matches_match_code_ci ON matches ((lower(match_code))) WHERE match_code IS NOT NULL",
        ],
    ),
    (
        "2.8.0",
        "Allow interrupted match status for restart/crash recovery",
        [
            "ALTER TABLE matches DROP CONSTRAINT IF EXISTS chk_match_status",
            """
            ALTER TABLE matches
            ADD CONSTRAINT chk_match_status CHECK (
                status IN ('in_progress', 'completed', 'interrupted', 'abandoned', 'disputed')
            )
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
        logger.warning("Applying database migration %s", version)
        checksum = hashlib.sha256("\n".join(stmt.strip() for stmt in statements).encode("utf-8")).hexdigest()
        try:
            with database.transaction() as cur:
                for stmt in statements:
                    cur.execute(stmt.strip())
                cur.execute(
                    """
                    INSERT INTO database_migrations (version, description, checksum)
                    VALUES (%s, %s, %s);
                    """,
                    (version, description, checksum),
                )
        except Exception:
            logger.exception("Migration %s failed", version)
            raise
        logger.warning("Migration %s applied successfully", version)
