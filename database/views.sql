-- PlayCord Database Views
-- Common query patterns as materialized views for performance

-- ============================================================================
-- VIEW: v_active_leaderboard
-- Active leaderboard with win rates and conservative ratings
-- ============================================================================
CREATE OR REPLACE VIEW v_active_leaderboard AS
SELECT 
    ugr.rating_id,
    ugr.user_id,
    u.username,
    ugr.guild_id,
    ugr.game_id,
    g.display_name as game_name,
    ugr.mu,
    ugr.sigma,
    (ugr.mu - 3 * ugr.sigma) as conservative_rating,
    ugr.matches_played,
    ugr.wins,
    ugr.losses,
    ugr.draws,
    CASE 
        WHEN (ugr.matches_played - ugr.draws) > 0 
        THEN ROUND(100.0 * ugr.wins / (ugr.matches_played - ugr.draws), 2)
        ELSE 0.0
    END as win_rate_pct,
    ugr.last_played,
    ugr.updated_at
FROM user_game_ratings ugr
JOIN users u ON ugr.user_id = u.user_id
JOIN games g ON ugr.game_id = g.game_id
WHERE ugr.matches_played >= 5  -- Minimum matches for ranking
AND u.is_active = TRUE
AND g.is_active = TRUE
ORDER BY ugr.guild_id, ugr.game_id, conservative_rating DESC;

COMMENT ON VIEW v_active_leaderboard IS 'Leaderboard with minimum match requirement and win rates';


-- ============================================================================
-- VIEW: v_recent_activity
-- Recent match activity across all guilds
-- ============================================================================
CREATE OR REPLACE VIEW v_recent_activity AS
SELECT 
    m.match_id,
    m.guild_id,
    m.game_id,
    g.display_name as game_name,
    m.started_at,
    m.ended_at,
    m.status,
    m.is_rated,
    COUNT(DISTINCT mp.user_id) as player_count,
    ARRAY_AGG(DISTINCT u.username ORDER BY u.username) as players,
    CASE 
        WHEN m.ended_at IS NOT NULL 
        THEN EXTRACT(EPOCH FROM (m.ended_at - m.started_at))::INTEGER
        ELSE NULL
    END as duration_seconds
FROM matches m
JOIN games g ON m.game_id = g.game_id
LEFT JOIN match_participants mp ON m.match_id = mp.match_id
LEFT JOIN users u ON mp.user_id = u.user_id
WHERE m.ended_at > NOW() - INTERVAL '7 days'
   OR m.status = 'in_progress'
GROUP BY m.match_id, g.display_name
ORDER BY m.ended_at DESC NULLS FIRST, m.started_at DESC;

COMMENT ON VIEW v_recent_activity IS 'Recent and ongoing matches with player info';


-- ============================================================================
-- VIEW: v_player_stats
-- Comprehensive player statistics per game
-- ============================================================================
CREATE OR REPLACE VIEW v_player_stats AS
SELECT 
    u.user_id,
    u.username,
    u.is_bot,
    ugr.guild_id,
    g.game_id,
    g.display_name as game_name,
    ugr.mu,
    ugr.sigma,
    (ugr.mu - 3 * ugr.sigma) as conservative_rating,
    ugr.matches_played,
    ugr.wins,
    ugr.losses,
    ugr.draws,
    CASE 
        WHEN (ugr.matches_played - ugr.draws) > 0 
        THEN ROUND(100.0 * ugr.wins / (ugr.matches_played - ugr.draws), 2)
        ELSE 0.0
    END as win_rate_pct,
    ugr.last_played,
    EXTRACT(EPOCH FROM (NOW() - ugr.last_played))::INTEGER / 86400 as days_since_last_game,
    CASE 
        WHEN ugr.sigma > ((g.rating_config->>'sigma')::DOUBLE PRECISION) * ugr.mu * 0.5
        THEN TRUE
        ELSE FALSE
    END as is_uncertain,
    rh.timestamp as last_rating_change,
    rh.mu_before as previous_mu,
    rh.sigma_before as previous_sigma,
    (rh.mu_after - rh.mu_before) as last_mu_change
FROM users u
JOIN user_game_ratings ugr ON u.user_id = ugr.user_id
JOIN games g ON ugr.game_id = g.game_id
LEFT JOIN LATERAL (
    SELECT 
        history_id,
        mu_before, 
        sigma_before,
        mu_after,
        sigma_after,
        timestamp 
    FROM rating_history
    WHERE user_id = u.user_id 
      AND game_id = ugr.game_id
      AND guild_id = ugr.guild_id
    ORDER BY timestamp DESC 
    LIMIT 1
) rh ON true
WHERE u.is_active = TRUE;

COMMENT ON VIEW v_player_stats IS 'Comprehensive player statistics with rating trends';


-- ============================================================================
-- VIEW: v_global_leaderboard
-- Global cross-guild leaderboard
-- ============================================================================
CREATE OR REPLACE VIEW v_global_leaderboard AS
SELECT 
    gr.user_id,
    u.username,
    gr.game_id,
    g.display_name as game_name,
    gr.global_mu,
    gr.global_sigma,
    (gr.global_mu - 3 * gr.global_sigma) as conservative_rating,
    gr.total_matches,
    ARRAY_LENGTH(gr.guilds_played_in, 1) as guild_count,
    gr.last_updated,
    ROW_NUMBER() OVER (
        PARTITION BY gr.game_id 
        ORDER BY (gr.global_mu - 3 * gr.global_sigma) DESC
    ) as global_rank
FROM global_ratings gr
JOIN users u ON gr.user_id = u.user_id
JOIN games g ON gr.game_id = g.game_id
WHERE u.is_active = TRUE
  AND g.is_active = TRUE
  AND gr.total_matches >= 10  -- Minimum for global ranking
ORDER BY gr.game_id, conservative_rating DESC;

COMMENT ON VIEW v_global_leaderboard IS 'Global leaderboard across all guilds';


-- ============================================================================
-- VIEW: v_match_summary
-- Detailed match information with participants
-- ============================================================================
CREATE OR REPLACE VIEW v_match_summary AS
SELECT 
    m.match_id,
    m.game_id,
    g.display_name as game_name,
    m.guild_id,
    m.channel_id,
    m.thread_id,
    m.started_at,
    m.ended_at,
    m.status,
    m.is_rated,
    CASE 
        WHEN m.ended_at IS NOT NULL 
        THEN EXTRACT(EPOCH FROM (m.ended_at - m.started_at))::INTEGER
        ELSE EXTRACT(EPOCH FROM (NOW() - m.started_at))::INTEGER
    END as duration_seconds,
    COUNT(DISTINCT mp.user_id) as player_count,
    ARRAY_AGG(
        json_build_object(
            'user_id', mp.user_id,
            'username', u.username,
            'player_number', mp.player_number,
            'final_ranking', mp.final_ranking,
            'mu_delta', mp.mu_delta,
            'sigma_delta', mp.sigma_delta
        ) ORDER BY mp.player_number
    ) as participants,
    (SELECT COUNT(*) FROM moves WHERE match_id = m.match_id) as move_count
FROM matches m
JOIN games g ON m.game_id = g.game_id
LEFT JOIN match_participants mp ON m.match_id = mp.match_id
LEFT JOIN users u ON mp.user_id = u.user_id
GROUP BY m.match_id, g.display_name
ORDER BY m.started_at DESC;

COMMENT ON VIEW v_match_summary IS 'Comprehensive match information with participants';


-- ============================================================================
-- VIEW: v_user_match_history
-- User's match history with outcomes
-- ============================================================================
CREATE OR REPLACE VIEW v_user_match_history AS
SELECT 
    mp.user_id,
    u.username,
    m.match_id,
    m.game_id,
    g.display_name as game_name,
    m.guild_id,
    m.started_at,
    m.ended_at,
    m.is_rated,
    mp.player_number,
    mp.final_ranking,
    mp.score,
    mp.mu_before,
    mp.sigma_before,
    mp.mu_delta,
    mp.sigma_delta,
    (mp.mu_before + mp.mu_delta) as mu_after,
    (mp.sigma_before + mp.sigma_delta) as sigma_after,
    CASE 
        WHEN mp.final_ranking = 1 THEN 'win'
        WHEN mp.final_ranking > 1 THEN 'loss'
        ELSE 'draw'
    END as outcome,
    COUNT(*) OVER (
        PARTITION BY mp.user_id, m.game_id 
        ORDER BY m.ended_at
    ) as game_sequence_number
FROM match_participants mp
JOIN matches m ON mp.match_id = m.match_id
JOIN users u ON mp.user_id = u.user_id
JOIN games g ON m.game_id = g.game_id
WHERE m.status = 'completed'
ORDER BY mp.user_id, m.ended_at DESC;

COMMENT ON VIEW v_user_match_history IS 'User match history with outcomes and rating changes';


-- ============================================================================
-- VIEW: v_inactive_players
-- Players who haven't played in 30+ days
-- ============================================================================
CREATE OR REPLACE VIEW v_inactive_players AS
SELECT 
    ugr.user_id,
    u.username,
    ugr.guild_id,
    ugr.game_id,
    g.display_name as game_name,
    ugr.matches_played,
    ugr.last_played,
    EXTRACT(EPOCH FROM (NOW() - ugr.last_played))::INTEGER / 86400 as days_inactive,
    ugr.mu,
    ugr.sigma,
    ugr.last_sigma_increase,
    CASE 
        WHEN ugr.last_sigma_increase IS NULL 
        THEN 'never_decayed'
        WHEN ugr.last_sigma_increase < NOW() - INTERVAL '30 days'
        THEN 'needs_decay'
        ELSE 'recently_decayed'
    END as decay_status
FROM user_game_ratings ugr
JOIN users u ON ugr.user_id = u.user_id
JOIN games g ON ugr.game_id = g.game_id
WHERE ugr.last_played < NOW() - INTERVAL '30 days'
  AND u.is_active = TRUE
ORDER BY ugr.last_played ASC;

COMMENT ON VIEW v_inactive_players IS 'Players eligible for skill decay';


-- ============================================================================
-- VIEW: v_guild_activity_summary
-- Guild-level activity metrics
-- ============================================================================
CREATE OR REPLACE VIEW v_guild_activity_summary AS
SELECT 
    g.guild_id,
    g.is_active,
    COUNT(DISTINCT ugr.user_id) as total_players,
    COUNT(DISTINCT ugr.game_id) as games_played,
    SUM(ugr.matches_played) as total_matches,
    MAX(ugr.last_played) as last_activity,
    EXTRACT(EPOCH FROM (NOW() - MAX(ugr.last_played)))::INTEGER / 86400 as days_since_activity,
    COUNT(DISTINCT CASE WHEN ugr.last_played > NOW() - INTERVAL '7 days' THEN ugr.user_id END) as active_players_7d,
    COUNT(DISTINCT CASE WHEN ugr.last_played > NOW() - INTERVAL '30 days' THEN ugr.user_id END) as active_players_30d
FROM guilds g
LEFT JOIN user_game_ratings ugr ON g.guild_id = ugr.guild_id
GROUP BY g.guild_id
ORDER BY last_activity DESC NULLS LAST;

COMMENT ON VIEW v_guild_activity_summary IS 'Guild activity metrics and player counts';


-- ============================================================================
-- VIEW: v_game_popularity
-- Game popularity metrics across guilds
-- ============================================================================
CREATE OR REPLACE VIEW v_game_popularity AS
SELECT 
    gm.game_id,
    gm.game_name,
    gm.display_name,
    COUNT(DISTINCT ugr.guild_id) as guilds_playing,
    COUNT(DISTINCT ugr.user_id) as total_players,
    SUM(ugr.matches_played) as total_matches,
    COUNT(DISTINCT CASE WHEN ugr.last_played > NOW() - INTERVAL '7 days' THEN ugr.user_id END) as active_players_7d,
    MAX(ugr.last_played) as last_played,
    AVG(ugr.matches_played) as avg_matches_per_player,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ugr.mu - 3 * ugr.sigma) as median_rating
FROM games gm
LEFT JOIN user_game_ratings ugr ON gm.game_id = ugr.game_id
WHERE gm.is_active = TRUE
GROUP BY gm.game_id
ORDER BY total_matches DESC NULLS LAST;

COMMENT ON VIEW v_game_popularity IS 'Game popularity and engagement metrics';