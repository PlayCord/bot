"""
Apply versioned database migrations tracked in database_migrations.

The schema is now clean-slate again, so fresh installs bootstrap from a single
baseline and historical migrations are intentionally dropped.
"""

from __future__ import annotations

import hashlib
import re

from playcord.utils.logging_config import get_logger

logger = get_logger("database.migrations")

MIGRATIONS: list[tuple[str, str, list[str]]] = [
    (
        "1.0.0",
        "Baseline schema is provided by schema.sql; no historical patch chain remains.",
        [],
    ),
    (
        "1.0.1",
        "Register game_errored analytics type (some paths / buffered events use this name).",
        [
            """
            INSERT INTO analytics_event_types (event_type, description)
            VALUES (
                'game_errored',
                'Game or match error (legacy name; prefer error_occurred in new code)'
            )
            ON CONFLICT (event_type) DO UPDATE SET
                description = EXCLUDED.description;
            """,
        ],
    ),
    (
        "1.0.2",
        "Drop redundant bot_messages.payload_digest column.",
        [
            """
            ALTER TABLE IF EXISTS bot_messages
            DROP COLUMN IF EXISTS payload_digest;
            """,
        ],
    ),
    (
        "1.0.3",
        "Remove legacy bot_messages table; runtime now tracks owned messages in memory.",
        [
            """
            DROP TABLE IF EXISTS bot_messages;
            """,
        ],
    ),
    (
        "1.0.4",
        "Set user_game_ratings defaults to conservative-rating baseline (mu=1500, sigma=166.6666666667).",
        [
            """
            ALTER TABLE IF EXISTS user_game_ratings
            ALTER COLUMN mu SET DEFAULT 1500.0;
            """,
            """
            ALTER TABLE IF EXISTS user_game_ratings
            ALTER COLUMN sigma SET DEFAULT 166.6666666667;
            """,
        ],
    ),
    (
        "1.0.5",
        "Consolidate replay_events into match_moves; migrate data and drop replay_events table.",
        [
            # Migrate all replay_events to match_moves with kind='system'
            """
            INSERT INTO match_moves (match_id, user_id, move_number, kind, move_data, is_game_affecting, created_at)
            SELECT
                re.match_id,
                re.actor_user_id,
                (SELECT COALESCE(MAX(m.move_number), 0) FROM match_moves m WHERE m.match_id = re.match_id) + re.sequence_number,
                'system',
                re.payload,
                FALSE,
                re.created_at
            FROM replay_events re
            ORDER BY re.match_id, re.sequence_number
            ON CONFLICT DO NOTHING;
            """,
            # Drop the now-redundant replay_events table
            """
            DROP TABLE IF EXISTS replay_events;
            """,
        ],
    ),
    (
        "1.0.6",
        "Create AFTER UPDATE trigger on user_game_ratings to auto-log rating_history.",
        [
            # Function to auto-insert into rating_history on mu/sigma changes
            """
            CREATE OR REPLACE FUNCTION log_rating_history()
            RETURNS TRIGGER AS $$
            BEGIN
                IF (NEW.mu != OLD.mu OR NEW.sigma != OLD.sigma) THEN
                    INSERT INTO rating_history (user_id, guild_id, game_id, match_id, mu_before, sigma_before, mu_after, sigma_after)
                    VALUES (NEW.user_id, NULL, NEW.game_id, NULL, OLD.mu, OLD.sigma, NEW.mu, NEW.sigma)
                    ON CONFLICT DO NOTHING;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """,
            # Create trigger
            """
            DROP TRIGGER IF EXISTS trg_user_ratings_history ON user_game_ratings;
            CREATE TRIGGER trg_user_ratings_history
                AFTER UPDATE OF mu, sigma ON user_game_ratings
                FOR EACH ROW
                EXECUTE FUNCTION log_rating_history();
            """,
        ],
    ),
    (
        "1.0.7",
        "Partition analytics_events by month for efficient cleanup.",
        [
            # Create partitioned table (replace existing)
            """
            -- Create new partitioned table
            CREATE TABLE IF NOT EXISTS analytics_events_partitioned (
                event_id BIGSERIAL NOT NULL,
                event_type VARCHAR(100) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                user_id BIGINT,
                guild_id BIGINT,
                game_id INTEGER,
                match_id BIGINT,
                metadata JSONB DEFAULT '{}'::jsonb
            ) PARTITION BY RANGE (created_at);
            """,
            # Add constraints and foreign keys to partitioned table
            """
            ALTER TABLE analytics_events_partitioned
                ADD CONSTRAINT fk_event_type_part FOREIGN KEY (event_type)
                REFERENCES analytics_event_types (event_type) ON DELETE RESTRICT,
                ADD CONSTRAINT fk_event_user_part FOREIGN KEY (user_id)
                REFERENCES users (user_id) ON DELETE SET NULL,
                ADD CONSTRAINT fk_event_guild_part FOREIGN KEY (guild_id)
                REFERENCES guilds (guild_id) ON DELETE SET NULL,
                ADD CONSTRAINT fk_event_game_part FOREIGN KEY (game_id)
                REFERENCES games (game_id) ON DELETE SET NULL,
                ADD CONSTRAINT fk_event_match_part FOREIGN KEY (match_id)
                REFERENCES matches (match_id) ON DELETE SET NULL;
            """,
            # Migrate existing data to partitioned table
            """
            INSERT INTO analytics_events_partitioned (event_id, event_type, created_at, user_id, guild_id, game_id, match_id, metadata)
            SELECT event_id, event_type, created_at, user_id, guild_id, game_id, match_id, metadata
            FROM analytics_events;
            """,
            # Drop old table and rename new one
            """
            DROP TABLE IF EXISTS analytics_events;
            ALTER TABLE analytics_events_partitioned RENAME TO analytics_events;
            """,
            # Create initial partitions (current month and 3 months back)
            """
            CREATE TABLE IF NOT EXISTS analytics_events_y2026_m01 PARTITION OF analytics_events
                FOR VALUES FROM ('2026-01-01'::timestamptz) TO ('2026-02-01'::timestamptz);
            """,
            """
            CREATE TABLE IF NOT EXISTS analytics_events_y2026_m02 PARTITION OF analytics_events
                FOR VALUES FROM ('2026-02-01'::timestamptz) TO ('2026-03-01'::timestamptz);
            """,
            """
            CREATE TABLE IF NOT EXISTS analytics_events_y2026_m03 PARTITION OF analytics_events
                FOR VALUES FROM ('2026-03-01'::timestamptz) TO ('2026-04-01'::timestamptz);
            """,
            """
            CREATE TABLE IF NOT EXISTS analytics_events_y2026_m04 PARTITION OF analytics_events
                FOR VALUES FROM ('2026-04-01'::timestamptz) TO ('2026-05-01'::timestamptz);
            """,
            # Create function to auto-create partitions on INSERT
            """
            CREATE OR REPLACE FUNCTION create_analytics_partition_if_needed()
            RETURNS TRIGGER AS $$
            DECLARE
                partition_name TEXT;
                start_date TIMESTAMPTZ;
                end_date TIMESTAMPTZ;
            BEGIN
                partition_name := 'analytics_events_y' || TO_CHAR(NEW.created_at, 'YYYY') || '_m' || TO_CHAR(NEW.created_at, 'MM');
                start_date := DATE_TRUNC('month', NEW.created_at);
                end_date := DATE_TRUNC('month', NEW.created_at) + INTERVAL '1 month';
                
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = partition_name AND table_schema = 'public'
                ) THEN
                    EXECUTE FORMAT(
                        'CREATE TABLE %I PARTITION OF analytics_events FOR VALUES FROM (%L) TO (%L)',
                        partition_name, start_date, end_date
                    );
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """,
            # Attach trigger for auto-partition creation
            """
            DROP TRIGGER IF EXISTS trg_analytics_auto_partition ON analytics_events;
            CREATE TRIGGER trg_analytics_auto_partition
                BEFORE INSERT ON analytics_events
                FOR EACH ROW
                EXECUTE FUNCTION create_analytics_partition_if_needed();
            """,
            # Update cleanup_old_analytics to drop partitions instead of DELETE
            """
            DROP FUNCTION IF EXISTS cleanup_old_analytics(integer) CASCADE;
            CREATE OR REPLACE FUNCTION cleanup_old_analytics(
                days_to_keep INTEGER DEFAULT 90
            )
            RETURNS BIGINT AS $$
            DECLARE
                cutoff_date TIMESTAMPTZ;
                partition_name TEXT;
                deleted_count BIGINT := 0;
            BEGIN
                cutoff_date := NOW() - (days_to_keep || ' days')::INTERVAL;
                
                FOR partition_name IN
                    SELECT tablename FROM pg_tables 
                    WHERE tablename LIKE 'analytics_events_y%_m%' AND schemaname = 'public'
                LOOP
                    -- Extract year and month from partition name
                    IF to_date(SUBSTRING(partition_name FROM 18 FOR 7), 'YYYY_MM') < cutoff_date THEN
                        EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(partition_name);
                        deleted_count := deleted_count + 1;
                    END IF;
                END LOOP;
                
                RETURN deleted_count;
            END;
            $$ LANGUAGE plpgsql;
            """,
        ],
    ),
    (
        "1.0.8",
        "Fix apply_skill_decay to apply exponential penalty for missed intervals.",
        [
            # Update apply_skill_decay to calculate missed intervals and apply exponentially
            """
            DROP FUNCTION IF EXISTS apply_skill_decay(integer, double precision) CASCADE;
            
            CREATE OR REPLACE FUNCTION apply_skill_decay(
                days_inactive INTEGER DEFAULT 30,
                sigma_increase_factor DOUBLE PRECISION DEFAULT 0.1
            )
            RETURNS TABLE (
                user_id BIGINT,
                game_id INTEGER,
                old_sigma DOUBLE PRECISION,
                new_sigma DOUBLE PRECISION,
                days_since_play INTEGER,
                missed_intervals INTEGER
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
                        r.sigma AS old_sig,
                        r.sigma * POWER(1 + sigma_increase_factor, 
                            FLOOR(EXTRACT(EPOCH FROM (NOW() - r.last_played)) / (days_inactive * 86400))::INTEGER) AS new_sig,
                        EXTRACT(EPOCH FROM (NOW() - r.last_played))::INTEGER / 86400 AS days_inactive_calc,
                        FLOOR(EXTRACT(EPOCH FROM (NOW() - r.last_played)) / (days_inactive * 86400))::INTEGER AS intervals
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
                    decay_data.days_inactive_calc,
                    decay_data.intervals;
            END;
            $$ LANGUAGE plpgsql;
            """,
        ],
    ),
    (
        "1.0.9",
        "Make rating_history.match_id nullable to support non-match rating updates (skill decay, admin adjustments).",
        [
            # Alter rating_history.match_id to be nullable (NOT NULL -> NULL)
            """
            ALTER TABLE rating_history
            ALTER COLUMN match_id DROP NOT NULL;
            """,
            # Update trigger to accept NULL match_id (already does via ON CONFLICT DO NOTHING)
            """
            CREATE OR REPLACE FUNCTION log_rating_history()
            RETURNS TRIGGER AS $$
            BEGIN
                IF (NEW.mu != OLD.mu OR NEW.sigma != OLD.sigma) THEN
                    INSERT INTO rating_history (user_id, guild_id, game_id, match_id, mu_before, sigma_before, mu_after, sigma_after)
                    VALUES (NEW.user_id, NULL, NEW.game_id, NULL, OLD.mu, OLD.sigma, NEW.mu, NEW.sigma)
                    ON CONFLICT DO NOTHING;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """,
        ],
    ),
    (
        "1.1.0",
        "Backfill sigma < 0.001 to 0.001 minimum to satisfy CHECK constraint.",
        [
            # Backfill any sigma values below the minimum
            """
            UPDATE user_game_ratings
            SET sigma = 0.001
            WHERE sigma < 0.001;
            """,
        ],
    ),
    (
        "1.1.1",
        "Add CHECK constraint to enforce completed matches must have ended_at set.",
        [
            # First backfill any completed matches without ended_at
            """
            UPDATE matches
            SET ended_at = started_at + INTERVAL '30 minutes'
            WHERE status = 'completed' AND ended_at IS NULL;
            """,
            # Add constraint
            """
            ALTER TABLE matches
            ADD CONSTRAINT chk_completed_match_has_end_time
            CHECK (status != 'completed' OR ended_at IS NOT NULL);
            """,
        ],
    ),
    (
        "1.1.2",
        "Create trigger to enforce final_ranking on match_participants when match status is completed.",
        [
            # Create function to validate final_ranking on match completion
            """
            CREATE OR REPLACE FUNCTION validate_completed_match_rankings()
            RETURNS TRIGGER AS $$
            DECLARE
                missing_rankings INTEGER;
            BEGIN
                -- Only validate if transitioning to 'completed' status
                IF NEW.status = 'completed' AND OLD.status != 'completed' THEN
                    -- Check if all participants have final_ranking set
                    SELECT COUNT(*)
                    INTO missing_rankings
                    FROM match_participants
                    WHERE match_id = NEW.match_id
                    AND final_ranking IS NULL;
                    
                    IF missing_rankings > 0 THEN
                        RAISE EXCEPTION
                            'Cannot complete match % with % participants missing final_ranking',
                            NEW.match_id, missing_rankings;
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """,
            # Drop existing trigger if any
            """
            DROP TRIGGER IF EXISTS trg_validate_completed_match_rankings ON matches;
            """,
            # Create trigger on matches table
            """
            CREATE TRIGGER trg_validate_completed_match_rankings
                BEFORE UPDATE OF status ON matches
                FOR EACH ROW
                EXECUTE FUNCTION validate_completed_match_rankings();
            """,
        ],
    ),
    (
        "1.1.3",
        "Add is_deleted soft-delete columns and update cascade behavior to preserve history.",
        [
            # Add is_deleted column to users table
            """
            ALTER TABLE users
            ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE NOT NULL;
            """,
            # Add is_deleted column to user_game_ratings
            """
            ALTER TABLE user_game_ratings
            ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE NOT NULL;
            """,
            # Add is_deleted column to match_participants
            """
            ALTER TABLE match_participants
            ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE NOT NULL;
            """,
            # Add is_deleted column to match_moves
            """
            ALTER TABLE match_moves
            ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE NOT NULL;
            """,
            # Add is_deleted column to rating_history
            """
            ALTER TABLE rating_history
            ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE NOT NULL;
            """,
            # Create indexes on is_deleted columns for efficient filtering
            """
            CREATE INDEX IF NOT EXISTS idx_users_deleted ON users (is_deleted) WHERE is_deleted = FALSE;
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_user_ratings_deleted ON user_game_ratings (is_deleted) WHERE is_deleted = FALSE;
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_participants_deleted ON match_participants (is_deleted) WHERE is_deleted = FALSE;
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_moves_deleted ON match_moves (is_deleted) WHERE is_deleted = FALSE;
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_history_deleted ON rating_history (is_deleted) WHERE is_deleted = FALSE;
            """,
        ],
    ),
    (
        "1.1.4",
        "Update foreign key constraints to use ON DELETE SET NULL instead of CASCADE for user deletion.",
        [
            # Change user_game_ratings FK to SET NULL
            """
            ALTER TABLE user_game_ratings
            DROP CONSTRAINT fk_user_rating_user,
            ADD CONSTRAINT fk_user_rating_user FOREIGN KEY (user_id)
                REFERENCES users (user_id) ON DELETE SET NULL;
            """,
            # Change match_participants FK to SET NULL
            """
            ALTER TABLE match_participants
            DROP CONSTRAINT fk_participant_user,
            ADD CONSTRAINT fk_participant_user FOREIGN KEY (user_id)
                REFERENCES users (user_id) ON DELETE SET NULL;
            """,
            # Change match_moves FK to SET NULL (already has this)
            # No change needed - already uses ON DELETE CASCADE which is ok for moves
            # Change rating_history FK to SET NULL
            """
            ALTER TABLE rating_history
            DROP CONSTRAINT fk_history_user,
            ADD CONSTRAINT fk_history_user FOREIGN KEY (user_id)
                REFERENCES users (user_id) ON DELETE SET NULL;
            """,
            # Change analytics_events FK to SET NULL (already has this)
            # No change needed - already uses ON DELETE SET NULL
        ],
    ),
    (
        "1.2.0",
        "Consolidate conservative rating formula (mu - 3*sigma) into helper function.",
        [
            # Update calculate_conservative_rating function to accept confidence_intervals parameter
            """
            CREATE OR REPLACE FUNCTION calculate_conservative_rating(
                mu DOUBLE PRECISION,
                sigma DOUBLE PRECISION,
                confidence_intervals DOUBLE PRECISION DEFAULT 3.0
            )
            RETURNS DOUBLE PRECISION AS $$
            BEGIN
                RETURN mu - (confidence_intervals * sigma);
            END;
            $$ LANGUAGE plpgsql IMMUTABLE;
            """,
            # Recreate views to use the function instead of inline formula
            """
            CREATE OR REPLACE VIEW v_active_leaderboard AS
            SELECT 
                ugr.rating_id,
                ugr.user_id,
                u.username,
                ugr.game_id,
                g.display_name as game_name,
                ugr.mu,
                ugr.sigma,
                calculate_conservative_rating(ugr.mu, ugr.sigma) as conservative_rating,
                ugr.matches_played,
                COALESCE(mo.wins, 0)::INTEGER as wins,
                COALESCE(mo.losses, 0)::INTEGER as losses,
                COALESCE(mo.draws, 0)::INTEGER as draws,
                CASE 
                    WHEN (ugr.matches_played - COALESCE(mo.draws, 0)) > 0 
                    THEN ROUND(
                        100.0 * COALESCE(mo.wins, 0) / (ugr.matches_played - COALESCE(mo.draws, 0))::NUMERIC,
                        2
                    )
                    ELSE 0.0
                END as win_rate_pct,
                ugr.last_played,
                ugr.updated_at
            FROM user_game_ratings ugr
            JOIN users u ON ugr.user_id = u.user_id
            JOIN games g ON ugr.game_id = g.game_id
            LEFT JOIN v_match_outcomes mo ON mo.user_id = ugr.user_id AND mo.game_id = ugr.game_id
            WHERE ugr.matches_played >= 5
            AND u.is_active = TRUE
            AND g.is_active = TRUE
            ORDER BY ugr.game_id, conservative_rating DESC;
            """,
            """
            CREATE OR REPLACE VIEW v_player_stats AS
            SELECT 
                u.user_id,
                u.username,
                u.is_bot,
                g.game_id,
                g.display_name as game_name,
                ugr.mu,
                ugr.sigma,
                calculate_conservative_rating(ugr.mu, ugr.sigma) as conservative_rating,
                ugr.matches_played,
                COALESCE(mo.wins, 0)::INTEGER as wins,
                COALESCE(mo.losses, 0)::INTEGER as losses,
                COALESCE(mo.draws, 0)::INTEGER as draws,
                CASE 
                    WHEN (ugr.matches_played - COALESCE(mo.draws, 0)) > 0 
                    THEN ROUND(
                        100.0 * COALESCE(mo.wins, 0) / (ugr.matches_played - COALESCE(mo.draws, 0))::NUMERIC,
                        2
                    )
                    ELSE 0.0
                END as win_rate_pct,
                ugr.last_played,
                EXTRACT(EPOCH FROM (NOW() - ugr.last_played))::INTEGER / 86400 as days_since_last_game,
                rh.created_at as last_rating_change,
                rh.mu_before as previous_mu,
                rh.sigma_before as previous_sigma,
                (rh.mu_after - rh.mu_before) as last_mu_change
            FROM users u
            JOIN user_game_ratings ugr ON u.user_id = ugr.user_id
            JOIN games g ON ugr.game_id = g.game_id
            LEFT JOIN v_match_outcomes mo ON mo.user_id = ugr.user_id AND mo.game_id = ugr.game_id
            LEFT JOIN LATERAL (
                SELECT 
                    history_id,
                    mu_before, 
                    sigma_before,
                    mu_after,
                    sigma_after,
                    created_at 
                FROM rating_history
                WHERE user_id = u.user_id 
                  AND game_id = ugr.game_id
                ORDER BY created_at DESC 
                LIMIT 1
            ) rh ON true
            WHERE u.is_active = TRUE;
            """,
            """
            CREATE OR REPLACE VIEW v_global_leaderboard AS
            SELECT 
                ugr.user_id,
                u.username,
                ugr.game_id,
                g.display_name as game_name,
                ugr.mu as global_mu,
                ugr.sigma as global_sigma,
                calculate_conservative_rating(ugr.mu, ugr.sigma) as conservative_rating,
                ugr.matches_played as total_matches,
                ugr.updated_at as last_updated,
                ROW_NUMBER() OVER (
                    PARTITION BY ugr.game_id 
                    ORDER BY calculate_conservative_rating(ugr.mu, ugr.sigma) DESC
                ) as global_rank
            FROM user_game_ratings ugr
            JOIN users u ON ugr.user_id = u.user_id
            JOIN games g ON ugr.game_id = g.game_id
            WHERE u.is_active = TRUE
              AND g.is_active = TRUE
              AND ugr.matches_played >= 10
            ORDER BY ugr.game_id, conservative_rating DESC;
            """,
            """
            CREATE OR REPLACE VIEW v_game_popularity AS
            SELECT 
                gm.game_id,
                gm.game_name,
                gm.display_name,
                COUNT(DISTINCT m.guild_id) as guilds_playing,
                COUNT(DISTINCT mp.user_id) as total_players,
                COUNT(DISTINCT m.match_id) as total_matches,
                COUNT(DISTINCT CASE WHEN m.ended_at > NOW() - INTERVAL '7 days' THEN mp.user_id END) as active_players_7d,
                MAX(m.ended_at) as last_played,
                (SELECT AVG(ugr.matches_played)::DOUBLE PRECISION FROM user_game_ratings ugr WHERE ugr.game_id = gm.game_id) as avg_matches_per_player,
                (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY calculate_conservative_rating(ugr.mu, ugr.sigma))
                 FROM user_game_ratings ugr WHERE ugr.game_id = gm.game_id) as median_rating
            FROM games gm
            LEFT JOIN matches m ON m.game_id = gm.game_id AND m.status = 'completed'
            LEFT JOIN match_participants mp ON mp.match_id = m.match_id
            WHERE gm.is_active = TRUE
            GROUP BY gm.game_id, gm.game_name, gm.display_name
            ORDER BY total_matches DESC NULLS LAST;
            """,
            # Recreate the leaderboard index with function-based expression
            """
            DROP INDEX IF EXISTS idx_rating_leaderboard;
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_rating_leaderboard ON user_game_ratings (
                game_id, (calculate_conservative_rating(mu, sigma)) DESC
            ) WHERE matches_played >= 5;
            """,
        ],
    ),
    (
        "1.2.1",
        "Add repair_matches_played_counts() function to detect rating counter drift.",
        [
            """
            CREATE OR REPLACE FUNCTION repair_matches_played_counts()
            RETURNS TABLE (
                user_id BIGINT,
                game_id INTEGER,
                recorded_count INTEGER,
                actual_count INTEGER,
                drift INTEGER
            ) AS $$
            BEGIN
                RETURN QUERY
                SELECT 
                    ugr.user_id,
                    ugr.game_id,
                    ugr.matches_played as recorded_count,
                    COUNT(*)::INTEGER as actual_count,
                    (COUNT(*)::INTEGER - ugr.matches_played) as drift
                FROM user_game_ratings ugr
                LEFT JOIN match_participants mp ON ugr.user_id = mp.user_id 
                    AND mp.is_deleted = FALSE
                LEFT JOIN matches m ON mp.match_id = m.match_id 
                    AND m.game_id = ugr.game_id
                    AND m.status = 'completed'
                GROUP BY ugr.user_id, ugr.game_id, ugr.matches_played
                HAVING COUNT(*)::INTEGER != ugr.matches_played
                ORDER BY ABS(COUNT(*)::INTEGER - ugr.matches_played) DESC;
            END;
            $$ LANGUAGE plpgsql;
            """,
        ],
    ),
    (
        "1.2.2",
        "Auto-sequence movement recording and add player count validation trigger.",
        [
            # Create player count validation trigger
            """
            CREATE OR REPLACE FUNCTION validate_player_counts()
            RETURNS TRIGGER AS $$
            DECLARE
                player_count INTEGER;
                min_players INTEGER;
                max_players INTEGER;
            BEGIN
                -- Get current player count (after INSERT/DELETE)
                SELECT COUNT(*) INTO player_count 
                FROM match_participants 
                WHERE match_id = NEW.match_id 
                  AND is_deleted = FALSE;
                
                -- Get game limits
                SELECT g.min_players, g.max_players INTO min_players, max_players
                FROM matches m
                JOIN games g ON m.game_id = g.game_id
                WHERE m.match_id = NEW.match_id;
                
                -- Validate player count is within bounds
                IF player_count < min_players THEN
                    RAISE EXCEPTION 
                        'Cannot have less than % players (game minimum). Currently: %',
                        min_players, player_count;
                END IF;
                
                IF player_count > max_players THEN
                    RAISE EXCEPTION 
                        'Cannot have more than % players (game maximum). Currently: %',
                        max_players, player_count;
                END IF;
                
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """,
            """
            DROP TRIGGER IF EXISTS trg_validate_player_counts ON match_participants;
            """,
            """
            CREATE TRIGGER trg_validate_player_counts
                AFTER INSERT OR DELETE ON match_participants
                FOR EACH ROW
                EXECUTE FUNCTION validate_player_counts();
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
        checksum = hashlib.sha256(
            "\n".join(stmt.strip() for stmt in statements).encode("utf-8")
        ).hexdigest()
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
