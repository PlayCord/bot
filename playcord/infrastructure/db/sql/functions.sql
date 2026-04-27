-- PlayCord PostgreSQL Functions
-- Auxiliary SQL functions intentionally kept compatible with schema.sql.
-- Core integrity triggers live in schema.sql.

-- Remove legacy trigger/function artifacts that conflict with deferred validation design.
DROP TRIGGER IF EXISTS trg_matches_completed_counts ON matches;
DROP TRIGGER IF EXISTS trg_enforce_min_rating ON user_game_ratings;
DROP TRIGGER IF EXISTS trg_validate_player_counts ON match_participants;
DROP TRIGGER IF EXISTS trg_validate_player_numbers ON match_participants;
DROP TRIGGER IF EXISTS trg_log_user_deletion ON users;

DROP FUNCTION IF EXISTS apply_completed_match_to_rating_counts() CASCADE;
DROP FUNCTION IF EXISTS enforce_user_game_rating_floors() CASCADE;
DROP FUNCTION IF EXISTS validate_player_counts() CASCADE;
DROP FUNCTION IF EXISTS validate_player_numbers() CASCADE;
DROP FUNCTION IF EXISTS log_user_deletion() CASCADE;

-- Conservative leaderboard score helper.
CREATE OR REPLACE FUNCTION calculate_conservative_rating(
    mu DOUBLE PRECISION,
    sigma DOUBLE PRECISION,
    confidence_intervals DOUBLE PRECISION DEFAULT 3.0
)
RETURNS DOUBLE PRECISION
LANGUAGE SQL
IMMUTABLE
AS
$$
SELECT mu - (confidence_intervals * sigma);
$$;

COMMENT ON FUNCTION calculate_conservative_rating IS
'Calculate conservative rating for leaderboard ordering. Default is mu - 3*sigma.';

-- Repair matches_played counters from authoritative completed-match participation.
CREATE OR REPLACE FUNCTION sync_games_played_counts()
RETURNS INTEGER
LANGUAGE plpgsql
AS
$$
DECLARE
    updated_count INTEGER;
BEGIN
    UPDATE user_game_ratings ugr
    SET matches_played = COALESCE((
        SELECT COUNT(*)::INTEGER
        FROM match_participants mp
        JOIN matches m ON m.match_id = mp.match_id
        WHERE mp.user_id = ugr.user_id
          AND mp.is_deleted = FALSE
          AND m.game_id = ugr.game_id
          AND m.status = 'completed'
    ), 0),
        updated_at = NOW();

    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RETURN updated_count;
END;
$$;

COMMENT ON FUNCTION sync_games_played_counts IS
'Recompute matches_played from completed matches (repair drift).';
