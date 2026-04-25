-- PlayCord PostgreSQL Functions
-- Stored procedures and triggers for automation

-- ============================================================================
-- FUNCTION: apply_skill_decay
-- Increases sigma for inactive players to reflect skill uncertainty
-- ============================================================================
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
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION apply_skill_decay IS 'Apply skill decay to inactive players by increasing sigma';


-- ============================================================================
-- FUNCTION: calculate_conservative_rating
-- Helper function to calculate conservative rating (mu - confidence_intervals*sigma)
-- ============================================================================
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

COMMENT ON FUNCTION calculate_conservative_rating IS 'Calculate conservative rating for leaderboard ordering. Default uses 3 sigma (99.7% confidence interval).';


-- ============================================================================
-- FUNCTION: repair_matches_played_counts
-- Detect and report drift between matches_played counter and actual completed matches
-- ============================================================================
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

COMMENT ON FUNCTION repair_matches_played_counts IS 'Detect drift between recorded matches_played counter and actual completed matches. Returns records with mismatches.';


-- ============================================================================
-- FUNCTION: get_head_to_head_stats
-- Get head-to-head statistics between two players
-- ============================================================================
CREATE OR REPLACE FUNCTION get_head_to_head_stats(
    p_user1_id BIGINT,
    p_user2_id BIGINT,
    p_game_id INTEGER DEFAULT NULL
)
RETURNS TABLE (
    game_id INTEGER,
    game_name VARCHAR,
    total_matches BIGINT,
    user1_wins BIGINT,
    user2_wins BIGINT,
    draws BIGINT,
    last_match_date TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        m.game_id,
        g.display_name,
        COUNT(*) as total_matches,
        SUM(CASE WHEN mp1.final_ranking < mp2.final_ranking THEN 1 ELSE 0 END) as user1_wins,
        SUM(CASE WHEN mp2.final_ranking < mp1.final_ranking THEN 1 ELSE 0 END) as user2_wins,
        SUM(CASE WHEN mp1.final_ranking = mp2.final_ranking THEN 1 ELSE 0 END) as draws,
        MAX(m.ended_at) as last_match_date
    FROM matches m
    JOIN games g ON m.game_id = g.game_id
    JOIN match_participants mp1 ON m.match_id = mp1.match_id AND mp1.user_id = p_user1_id
    JOIN match_participants mp2 ON m.match_id = mp2.match_id AND mp2.user_id = p_user2_id
    WHERE m.status = 'completed'
      AND (p_game_id IS NULL OR m.game_id = p_game_id)
    GROUP BY m.game_id, g.display_name
    ORDER BY total_matches DESC;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_head_to_head_stats IS 'Get head-to-head match statistics between two players';


-- ============================================================================
-- FUNCTION: cleanup_old_analytics
-- Archive or delete old analytics events
-- ============================================================================
CREATE OR REPLACE FUNCTION cleanup_old_analytics(
    days_to_keep INTEGER DEFAULT 90
)
RETURNS BIGINT AS $$
DECLARE
    deleted_count BIGINT;
BEGIN
    DELETE FROM analytics_events
    WHERE created_at < NOW() - (days_to_keep || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_old_analytics IS 'Delete analytics events older than specified days';


-- ============================================================================
-- FUNCTION: archive_old_matches
-- Soft delete old completed matches by updating metadata
-- ============================================================================
CREATE OR REPLACE FUNCTION archive_old_matches(
    days_old INTEGER DEFAULT 365
)
RETURNS BIGINT AS $$
DECLARE
    archived_count BIGINT;
BEGIN
    UPDATE matches
    SET metadata = jsonb_set(
        COALESCE(metadata, '{}'::jsonb),
        '{archived}',
        'true'::jsonb
    )
    WHERE ended_at < NOW() - (days_old || ' days')::INTERVAL
      AND status = 'completed'
      AND NOT (metadata ? 'archived' AND (metadata->>'archived')::boolean = true);

    GET DIAGNOSTICS archived_count = ROW_COUNT;
    RETURN archived_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION archive_old_matches IS 'Mark old matches as archived in metadata';

-- ============================================================================
-- FUNCTION: validate_move_sequence
-- Check if moves in a match have a valid sequence (no gaps)
-- ============================================================================
CREATE OR REPLACE FUNCTION validate_move_sequence(
    p_match_id BIGINT
)
RETURNS BOOLEAN AS $$
DECLARE
    move_count INTEGER;
    max_move_number INTEGER;
BEGIN
    SELECT COUNT(*), MAX(move_number)
    INTO move_count, max_move_number
    FROM match_moves
    WHERE match_id = p_match_id;

    RETURN (move_count = 0)
        OR (
            move_count = max_move_number
            AND max_move_number IS NOT NULL
            AND (
                SELECT MIN(move_number) FROM match_moves WHERE match_id = p_match_id
            ) = 1
        );
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION validate_move_sequence IS 'Check for gaps in move sequence';


-- ============================================================================
-- FUNCTION: get_player_activity_summary
-- Get activity summary for a player
-- ============================================================================
CREATE OR REPLACE FUNCTION get_player_activity_summary(
    p_user_id BIGINT,
    p_days INTEGER DEFAULT 30
)
RETURNS TABLE (
    total_matches BIGINT,
    total_wins BIGINT,
    total_losses BIGINT,
    total_draws BIGINT,
    games_played INTEGER,
    guilds_played INTEGER,
    avg_matches_per_day NUMERIC,
    favorite_game VARCHAR,
    best_game VARCHAR,
    most_active_guild BIGINT
) AS $$
BEGIN
    RETURN QUERY
    WITH match_stats AS (
        SELECT
            COUNT(*)::BIGINT as match_count,
            SUM(CASE WHEN mp.final_ranking = 1 THEN 1 ELSE 0 END)::BIGINT as wins,
            SUM(CASE WHEN mp.final_ranking > 1 THEN 1 ELSE 0 END)::BIGINT as losses,
            SUM(CASE WHEN mp.final_ranking IS NULL THEN 1 ELSE 0 END)::BIGINT as unknown_results,
            SUM(CASE WHEN mp.final_ranking = 1 AND COALESCE(r1.rank1_count, 0) > 1 THEN 1 ELSE 0 END)::BIGINT as draws,
            COUNT(DISTINCT m.game_id)::INTEGER as game_count,
            COUNT(DISTINCT m.guild_id)::INTEGER as guild_count,
            COUNT(*)::NUMERIC / NULLIF(p_days, 0) as matches_per_day
        FROM match_participants mp
        JOIN matches m ON mp.match_id = m.match_id
        LEFT JOIN (
            SELECT match_id, COUNT(*)::INTEGER AS rank1_count
            FROM match_participants
            WHERE final_ranking = 1
            GROUP BY match_id
        ) r1 ON r1.match_id = mp.match_id
        WHERE mp.user_id = p_user_id
          AND m.ended_at > NOW() - (p_days || ' days')::INTERVAL
          AND m.status = 'completed'
    ),
    game_stats AS (
        SELECT
            g.display_name as fav_game,
            COUNT(*) as game_match_count
        FROM match_participants mp
        JOIN matches m ON mp.match_id = m.match_id
        JOIN games g ON m.game_id = g.game_id
        WHERE mp.user_id = p_user_id
          AND m.ended_at > NOW() - (p_days || ' days')::INTERVAL
        GROUP BY g.display_name
        ORDER BY game_match_count DESC
        LIMIT 1
    ),
    best_game_stats AS (
        SELECT
            g.display_name as best_game_name
        FROM user_game_ratings ugr
        JOIN games g ON ugr.game_id = g.game_id
        WHERE ugr.user_id = p_user_id
          AND ugr.matches_played >= 5
        ORDER BY calculate_conservative_rating(ugr.mu, ugr.sigma) DESC
        LIMIT 1
    ),
    guild_stats AS (
        SELECT
            m.guild_id as most_active_guild_id
        FROM match_participants mp
        JOIN matches m ON mp.match_id = m.match_id
        WHERE mp.user_id = p_user_id
          AND m.ended_at > NOW() - (p_days || ' days')::INTERVAL
        GROUP BY m.guild_id
        ORDER BY COUNT(*) DESC
        LIMIT 1
    )
    SELECT
        COALESCE(ms.match_count, 0),
        COALESCE(ms.wins, 0),
        COALESCE(ms.losses, 0),
        COALESCE(ms.draws, 0),
        COALESCE(ms.game_count, 0),
        COALESCE(ms.guild_count, 0),
        COALESCE(ROUND(ms.matches_per_day, 2), 0.0),
        gs.fav_game,
        bgs.best_game_name,
        glds.most_active_guild_id
    FROM (SELECT 1 AS anchor) seed
    LEFT JOIN match_stats ms ON true
    LEFT JOIN LATERAL (SELECT fav_game FROM game_stats) gs ON true
    LEFT JOIN LATERAL (SELECT best_game_name FROM best_game_stats) bgs ON true
    LEFT JOIN LATERAL (SELECT most_active_guild_id FROM guild_stats) glds ON true;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_player_activity_summary IS 'Get comprehensive activity summary for a player';


-- ============================================================================
-- FUNCTION: calculate_win_loss_tie_from_ranking
-- Win / loss / draw from final_ranking and tie-for-first (FFA-safe)
-- ============================================================================
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
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION calculate_win_loss_tie_from_ranking IS
'Derive win/loss/draw flags from final_ranking and tie-for-first count (FFA-safe).';


-- ============================================================================
-- FUNCTION: sync_games_played_counts
-- Recompute matches_played from completed matches
-- ============================================================================
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
          AND m.game_id = ugr.game_id
          AND m.status = 'completed'
    ), 0);
    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION sync_games_played_counts IS
'Recompute matches_played from completed matches (repair drift).';


-- ============================================================================
-- TRIGGER: increment matches_played when a match completes
-- ============================================================================
CREATE OR REPLACE FUNCTION apply_completed_match_to_rating_counts()
RETURNS TRIGGER AS $$
BEGIN
        -- OLD.status is an enum type (match_status). Coalescing it with a text
        -- literal ('') causes an invalid input value error when OLD.status is
        -- NULL because COALESCE attempts to resolve a common type between the
        -- arguments. Cast the enum to text first so COALESCE operates on text and
        -- avoids invalid enum literal errors.
        IF NEW.status = 'completed' AND COALESCE(OLD.status::text, '') <> 'completed' THEN
        UPDATE user_game_ratings ugr
        SET
            matches_played = matches_played + 1,
            last_played = COALESCE(NEW.ended_at, NOW()),
            updated_at = NOW()
        FROM match_participants mp
        WHERE mp.match_id = NEW.match_id
          AND ugr.user_id = mp.user_id
          AND ugr.game_id = NEW.game_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_matches_completed_counts ON matches;
CREATE TRIGGER trg_matches_completed_counts
    AFTER UPDATE OF status ON matches
    FOR EACH ROW
    EXECUTE FUNCTION apply_completed_match_to_rating_counts();


-- ============================================================================
-- TRIGGER: enforce rating floors from games.rating_config (min_mu, min_sigma)
-- ============================================================================
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
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_enforce_min_rating ON user_game_ratings;
CREATE TRIGGER trg_enforce_min_rating
    BEFORE INSERT OR UPDATE OF mu, sigma ON user_game_ratings
    FOR EACH ROW
    EXECUTE FUNCTION enforce_user_game_rating_floors();


-- ============================================================================
-- FUNCTION: validate_player_counts
-- Enforce min/max player counts from game configuration
-- ============================================================================
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

COMMENT ON FUNCTION validate_player_counts IS 'Enforce game min/max player count constraints on match_participants INSERT/DELETE';

DROP TRIGGER IF EXISTS trg_validate_player_counts ON match_participants;
CREATE TRIGGER trg_validate_player_counts
    AFTER INSERT OR DELETE ON match_participants
    FOR EACH ROW
    EXECUTE FUNCTION validate_player_counts();


-- ============================================================================
-- COMPLETE
-- ============================================================================
