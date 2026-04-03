"""
Apply versioned database migrations tracked in database_migrations.
Each migration is a list of SQL statements executed in one transaction.
"""

import logging
import re
from typing import List, Tuple

logger = logging.getLogger("playcord.database.migrations")

# (version, description, statements) — version must match database_migrations.chk_version_format
MIGRATIONS: List[Tuple[str, str, List[str]]] = [
    (
        "2.1.0",
        "Phase 1: rating floors, sync helpers, moves.is_game_affecting",
        [
            """
            UPDATE user_game_ratings SET sigma = 0.001 WHERE sigma < 0.001
            """,
            """
            UPDATE user_game_ratings SET mu = 0.0 WHERE mu < 0.0
            """,
            """
            UPDATE global_ratings SET global_sigma = 0.001 WHERE global_sigma < 0.001
            """,
            """
            UPDATE global_ratings SET global_mu = 0.0 WHERE global_mu < 0.0
            """,
            """
            ALTER TABLE games ADD COLUMN IF NOT EXISTS game_schema_version INTEGER DEFAULT 1 NOT NULL
            """,
            """
            ALTER TABLE moves ADD COLUMN IF NOT EXISTS is_game_affecting BOOLEAN DEFAULT TRUE NOT NULL
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_moves_game_affecting ON moves (is_game_affecting)
            WHERE is_game_affecting = TRUE
            """,
            """
            DO $c$
            BEGIN
                ALTER TABLE user_game_ratings DROP CONSTRAINT IF EXISTS chk_rating_positive;
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint c
                    JOIN pg_class t ON c.conrelid = t.oid
                    WHERE t.relname = 'user_game_ratings' AND c.conname = 'chk_rating_floor'
                ) THEN
                    ALTER TABLE user_game_ratings
                    ADD CONSTRAINT chk_rating_floor CHECK (mu >= 0.0 AND sigma >= 0.001);
                END IF;
            END $c$
            """,
            """
            DO $c$
            BEGIN
                ALTER TABLE global_ratings DROP CONSTRAINT IF EXISTS chk_global_rating_positive;
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint c
                    JOIN pg_class t ON c.conrelid = t.oid
                    WHERE t.relname = 'global_ratings' AND c.conname = 'chk_global_rating_floor'
                ) THEN
                    ALTER TABLE global_ratings
                    ADD CONSTRAINT chk_global_rating_floor
                    CHECK (global_mu >= 0.0 AND global_sigma >= 0.001);
                END IF;
            END $c$
            """,
            """
            CREATE OR REPLACE FUNCTION calculate_win_loss_tie_from_ranking(
                p_final_ranking INTEGER,
                p_match_id BIGINT
            )
            RETURNS TABLE (is_win BOOLEAN, is_loss BOOLEAN, is_draw BOOLEAN) AS $$
            DECLARE
                rank1_count INTEGER;
            BEGIN
                IF p_final_ranking IS NULL THEN
                    RETURN QUERY SELECT FALSE, FALSE, FALSE;
                    RETURN;
                END IF;
                SELECT COUNT(*) INTO rank1_count
                FROM match_participants mp
                WHERE mp.match_id = p_match_id AND mp.final_ranking = 1;
                IF p_final_ranking = 1 AND rank1_count > 1 THEN
                    RETURN QUERY SELECT FALSE, FALSE, TRUE;
                ELSIF p_final_ranking = 1 THEN
                    RETURN QUERY SELECT TRUE, FALSE, FALSE;
                ELSE
                    RETURN QUERY SELECT FALSE, TRUE, FALSE;
                END IF;
            END;
            $$ LANGUAGE plpgsql STABLE
            """,
            """
            COMMENT ON FUNCTION calculate_win_loss_tie_from_ranking IS
            'Derive win/loss/draw flags from final_ranking and tie-for-first count (FFA-safe).'
            """,
            """
            CREATE OR REPLACE FUNCTION sync_games_played_counts()
            RETURNS INTEGER AS $$
            DECLARE
                updated INTEGER;
            BEGIN
                UPDATE user_game_ratings ugr
                SET matches_played = COALESCE((
                    SELECT COUNT(*)::INTEGER
                    FROM match_participants mp
                    JOIN matches m ON mp.match_id = m.match_id
                    WHERE mp.user_id = ugr.user_id
                      AND m.guild_id = ugr.guild_id
                      AND m.game_id = ugr.game_id
                      AND m.status = 'completed'
                ), 0);
                GET DIAGNOSTICS updated = ROW_COUNT;
                RETURN updated;
            END;
            $$ LANGUAGE plpgsql
            """,
            """
            COMMENT ON FUNCTION sync_games_played_counts IS
            'Recompute matches_played from completed matches (repair drift).'
            """,
            """
            CREATE OR REPLACE FUNCTION enforce_user_game_rating_floors()
            RETURNS TRIGGER AS $$
            DECLARE
                min_mu DOUBLE PRECISION;
                min_sigma DOUBLE PRECISION;
            BEGIN
                SELECT
                    COALESCE((g.rating_config->>'min_mu')::DOUBLE PRECISION, 0.0),
                    COALESCE((g.rating_config->>'min_sigma')::DOUBLE PRECISION, 0.001)
                INTO min_mu, min_sigma
                FROM games g WHERE g.game_id = NEW.game_id;
                IF min_sigma < 0.001 THEN
                    min_sigma := 0.001;
                END IF;
                NEW.mu := GREATEST(NEW.mu, min_mu);
                NEW.sigma := GREATEST(NEW.sigma, min_sigma);
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """,
            """
            DROP TRIGGER IF EXISTS trg_enforce_min_rating ON user_game_ratings
            """,
            """
            CREATE TRIGGER trg_enforce_min_rating
                BEFORE INSERT OR UPDATE OF mu, sigma ON user_game_ratings
                FOR EACH ROW
                EXECUTE FUNCTION enforce_user_game_rating_floors()
            """,
            """
            CREATE OR REPLACE FUNCTION apply_skill_decay(
                days_inactive INTEGER DEFAULT 30,
                sigma_increase_factor DOUBLE PRECISION DEFAULT 0.1
            )
            RETURNS TABLE (
                user_id BIGINT,
                game_id INTEGER,
                guild_id BIGINT,
                old_sigma DOUBLE PRECISION,
                new_sigma DOUBLE PRECISION,
                days_since_play INTEGER
            ) AS $$
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
                        r.guild_id AS guildid,
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
                    decay_data.guildid,
                    decay_data.old_sig,
                    ugr.sigma,
                    decay_data.days_inactive_calc;
            END;
            $$ LANGUAGE plpgsql
            """,
            """
            CREATE OR REPLACE FUNCTION update_global_rating(
                p_user_id BIGINT,
                p_game_id INTEGER
            )
            RETURNS VOID AS $$
            DECLARE
                total_precision DOUBLE PRECISION;
                weighted_mu_sum DOUBLE PRECISION;
                guild_count INTEGER;
                guilds_array BIGINT[];
                new_global_mu DOUBLE PRECISION;
                new_global_sigma DOUBLE PRECISION;
                match_count INTEGER;
            BEGIN
                SELECT
                    SUM(1.0 / (sigma * sigma)) AS total_prec,
                    SUM(mu / (sigma * sigma)) AS weighted_mu,
                    COUNT(*) AS guild_cnt,
                    ARRAY_AGG(guild_id) AS guilds,
                    SUM(matches_played) AS total_matches
                INTO
                    total_precision,
                    weighted_mu_sum,
                    guild_count,
                    guilds_array,
                    match_count
                FROM user_game_ratings
                WHERE user_id = p_user_id
                  AND game_id = p_game_id
                  AND matches_played > 0;
                IF guild_count > 0 THEN
                    new_global_mu := weighted_mu_sum / total_precision;
                    new_global_sigma := SQRT(1.0 / total_precision);
                    new_global_mu := GREATEST(new_global_mu, 0.0);
                    new_global_sigma := GREATEST(new_global_sigma, 0.001);
                    INSERT INTO global_ratings (user_id, game_id, global_mu, global_sigma, total_matches, guilds_played_in, last_updated)
                    VALUES (p_user_id, p_game_id, new_global_mu, new_global_sigma, match_count, guilds_array, NOW())
                    ON CONFLICT (user_id, game_id)
                    DO UPDATE SET
                        global_mu = EXCLUDED.global_mu,
                        global_sigma = EXCLUDED.global_sigma,
                        total_matches = EXCLUDED.total_matches,
                        guilds_played_in = EXCLUDED.guilds_played_in,
                        last_updated = NOW();
                END IF;
            END;
            $$ LANGUAGE plpgsql
            """,
        ],
    ),
    (
        "2.2.0",
        "Replay: JSONL action log on matches; drop random_seed",
        [
            """
            ALTER TABLE matches ADD COLUMN IF NOT EXISTS replay_log TEXT
            """,
            """
            ALTER TABLE matches DROP COLUMN IF EXISTS random_seed
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
