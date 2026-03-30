-- PlayCord PostgreSQL Functions
-- Stored procedures and triggers for automation

-- ============================================================================
-- FUNCTION: apply_skill_decay
-- Increases sigma for inactive players to reflect skill uncertainty
-- ============================================================================
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
        sigma = ugr.sigma * (1 + sigma_increase_factor),
        last_sigma_increase = NOW(),
        updated_at = NOW()
    FROM (
        SELECT 
            r.rating_id,
            r.user_id as uid,
            r.game_id as gid,
            r.guild_id as guildid,
            r.sigma as old_sig,
            r.sigma * (1 + sigma_increase_factor) as new_sig,
            EXTRACT(EPOCH FROM (NOW() - r.last_played))::INTEGER / 86400 as days_inactive_calc
        FROM user_game_ratings r
        WHERE r.last_played < NOW() - (days_inactive || ' days')::INTERVAL
          AND (r.last_sigma_increase IS NULL 
               OR r.last_sigma_increase < NOW() - (days_inactive || ' days')::INTERVAL)
    ) decay_data
    WHERE ugr.rating_id = decay_data.rating_id
    RETURNING 
        decay_data.uid,
        decay_data.gid,
        decay_data.guildid,
        decay_data.old_sig,
        decay_data.new_sig,
        decay_data.days_inactive_calc;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION apply_skill_decay IS 'Apply skill decay to inactive players by increasing sigma';


-- ============================================================================
-- FUNCTION: calculate_conservative_rating
-- Helper function to calculate conservative rating (mu - 3*sigma)
-- ============================================================================
CREATE OR REPLACE FUNCTION calculate_conservative_rating(
    mu DOUBLE PRECISION,
    sigma DOUBLE PRECISION
)
RETURNS DOUBLE PRECISION AS $$
BEGIN
    RETURN mu - (3.0 * sigma);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION calculate_conservative_rating IS 'Calculate conservative rating for leaderboard ordering';


-- ============================================================================
-- FUNCTION: get_user_rank
-- Get user's rank in a specific guild/game leaderboard
-- ============================================================================
CREATE OR REPLACE FUNCTION get_user_rank(
    p_user_id BIGINT,
    p_guild_id BIGINT,
    p_game_id INTEGER
)
RETURNS INTEGER AS $$
DECLARE
    user_rank INTEGER;
BEGIN
    SELECT rank INTO user_rank
    FROM (
        SELECT 
            user_id,
            ROW_NUMBER() OVER (
                ORDER BY (mu - 3 * sigma) DESC
            ) as rank
        FROM user_game_ratings
        WHERE guild_id = p_guild_id
          AND game_id = p_game_id
          AND matches_played >= 5
    ) ranked
    WHERE user_id = p_user_id;
    
    RETURN COALESCE(user_rank, -1);  -- -1 if not ranked
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_user_rank IS 'Get user rank in guild/game leaderboard (-1 if unranked)';


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
    WHERE timestamp < NOW() - (days_to_keep || ' days')::INTERVAL;
    
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
-- FUNCTION: update_global_rating
-- Calculate and update global rating for a user/game combination
-- Uses Bayesian aggregation across guilds
-- ============================================================================
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
    -- Calculate precision-weighted average across guilds
    SELECT 
        SUM(1.0 / (sigma * sigma)) as total_prec,
        SUM(mu / (sigma * sigma)) as weighted_mu,
        COUNT(*) as guild_cnt,
        ARRAY_AGG(guild_id) as guilds,
        SUM(matches_played) as total_matches
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
        -- Bayesian combination: mu = sum(mu_i / sigma_i^2) / sum(1 / sigma_i^2)
        new_global_mu := weighted_mu_sum / total_precision;
        -- Combined uncertainty: sigma = sqrt(1 / sum(1 / sigma_i^2))
        new_global_sigma := SQRT(1.0 / total_precision);
        
        -- Insert or update global rating
        INSERT INTO global_ratings (user_id, game_id, global_mu, global_sigma, total_matches, guilds_played_in, last_updated)
        VALUES (p_user_id, p_game_id, new_global_mu, new_global_sigma, match_count, guilds_array, NOW())
        ON CONFLICT (user_id, game_id) 
        DO UPDATE SET
            global_mu = new_global_mu,
            global_sigma = new_global_sigma,
            total_matches = match_count,
            guilds_played_in = guilds_array,
            last_updated = NOW();
    END IF;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION update_global_rating IS 'Calculate global rating using Bayesian combination across guilds';


-- ============================================================================
-- FUNCTION: batch_update_global_ratings
-- Update all global ratings for a specific game
-- ============================================================================
CREATE OR REPLACE FUNCTION batch_update_global_ratings(
    p_game_id INTEGER DEFAULT NULL
)
RETURNS BIGINT AS $$
DECLARE
    updated_count BIGINT := 0;
    user_game_rec RECORD;
BEGIN
    FOR user_game_rec IN
        SELECT DISTINCT user_id, game_id
        FROM user_game_ratings
        WHERE (p_game_id IS NULL OR game_id = p_game_id)
          AND matches_played > 0
    LOOP
        PERFORM update_global_rating(user_game_rec.user_id, user_game_rec.game_id);
        updated_count := updated_count + 1;
    END LOOP;
    
    RETURN updated_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION batch_update_global_ratings IS 'Recalculate global ratings for all users (optionally filtered by game)';


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
    FROM moves
    WHERE match_id = p_match_id;
    
    -- If move count equals max move number, sequence is valid (1, 2, 3, ..., n)
    RETURN (move_count = max_move_number) OR (move_count = 0);
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION validate_move_sequence IS 'Check for gaps in move sequence';


-- ============================================================================
-- FUNCTION: get_match_replay_data
-- Get all data needed to replay a match
-- ============================================================================
CREATE OR REPLACE FUNCTION get_match_replay_data(
    p_match_id BIGINT
)
RETURNS TABLE (
    match_info JSONB,
    participants JSONB,
    moves JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        to_jsonb(m.*) as match_info,
        (
            SELECT jsonb_agg(to_jsonb(mp.*) ORDER BY mp.player_number)
            FROM match_participants mp
            WHERE mp.match_id = p_match_id
        ) as participants,
        (
            SELECT jsonb_agg(to_jsonb(mv.*) ORDER BY mv.move_number)
            FROM moves mv
            WHERE mv.match_id = p_match_id
        ) as moves
    FROM matches m
    WHERE m.match_id = p_match_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_match_replay_data IS 'Get complete match data for replay';


-- ============================================================================
-- TRIGGER FUNCTION: prevent_rating_manipulation
-- Prevent manual rating manipulation (must go through proper channels)
-- ============================================================================
CREATE OR REPLACE FUNCTION prevent_direct_rating_updates()
RETURNS TRIGGER AS $$
BEGIN
    -- Allow updates if they come from the application (check if updated_at changed)
    -- This is a soft check - in production, use application-level permissions
    IF TG_OP = 'UPDATE' AND OLD.updated_at = NEW.updated_at THEN
        RAISE EXCEPTION 'Direct rating updates not allowed. Use match completion workflow.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Note: Commented out to allow flexibility during development
-- CREATE TRIGGER tr_prevent_rating_manipulation
--     BEFORE UPDATE ON user_game_ratings
--     FOR EACH ROW
--     EXECUTE FUNCTION prevent_direct_rating_updates();


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
            COUNT(*) as match_count,
            SUM(CASE WHEN mp.final_ranking = 1 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN mp.final_ranking > 1 THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN mp.final_ranking IS NULL THEN 1 ELSE 0 END) as draws,
            COUNT(DISTINCT m.game_id) as game_count,
            COUNT(DISTINCT m.guild_id) as guild_count,
            COUNT(*)::NUMERIC / NULLIF(p_days, 0) as matches_per_day
        FROM match_participants mp
        JOIN matches m ON mp.match_id = m.match_id
        WHERE mp.user_id = p_user_id
          AND m.ended_at > NOW() - (p_days || ' days')::INTERVAL
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
        ORDER BY (ugr.mu - 3 * ugr.sigma) DESC
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
        ms.match_count,
        ms.wins,
        ms.losses,
        ms.draws,
        ms.game_count,
        ms.guild_count,
        ROUND(ms.matches_per_day, 2),
        gs.fav_game,
        bgs.best_game_name,
        glds.most_active_guild_id
    FROM match_stats ms
    CROSS JOIN game_stats gs
    CROSS JOIN best_game_stats bgs
    CROSS JOIN guild_stats glds;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_player_activity_summary IS 'Get comprehensive activity summary for a player';


-- ============================================================================
-- COMPLETE
-- ============================================================================
