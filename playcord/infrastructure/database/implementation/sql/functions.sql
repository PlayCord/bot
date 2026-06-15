-- PlayCord PostgreSQL Functions
-- Auxiliary SQL functions intentionally kept compatible with schema.sql.
-- Core integrity triggers live in schema.sql.

-- Remove legacy trigger/function artifacts that conflict with deferred validation design.
DROP TRIGGER IF EXISTS trg_matches_completed_counts ON matches;
DROP TRIGGER IF EXISTS trg_validate_player_counts ON match_participants;
DROP TRIGGER IF EXISTS trg_validate_player_numbers ON match_participants;
DROP TRIGGER IF EXISTS trg_log_user_deletion ON users;

DROP FUNCTION IF EXISTS apply_completed_match_to_rating_counts() CASCADE;
DROP FUNCTION IF EXISTS enforce_user_game_rating_floors() CASCADE;
DROP FUNCTION IF EXISTS validate_player_counts() CASCADE;
DROP FUNCTION IF EXISTS validate_player_numbers() CASCADE;
DROP FUNCTION IF EXISTS log_user_deletion() CASCADE;
DROP FUNCTION IF EXISTS calculate_conservative_rating(DOUBLE PRECISION, DOUBLE PRECISION, DOUBLE PRECISION) CASCADE;
DROP FUNCTION IF EXISTS sync_games_played_counts() CASCADE;
