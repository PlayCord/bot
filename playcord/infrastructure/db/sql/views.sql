-- PlayCord Database Views
-- Common query patterns as materialized views for performance

-- ============================================================================
-- VIEW: v_match_outcomes
-- Shared win/loss/draw aggregation used by leaderboard/stats views
-- ============================================================================
CREATE OR REPLACE VIEW v_match_outcomes AS
SELECT
    mp.user_id,
    m.game_id,
    SUM(
        CASE
            WHEN mp.final_ranking = 1 AND COALESCE(r1.rank1_count, 0) = 1 THEN 1
            ELSE 0
        END
    )::INTEGER AS wins,
    SUM(
        CASE
            WHEN mp.final_ranking = 1 AND COALESCE(r1.rank1_count, 0) > 1 THEN 1
            ELSE 0
        END
    )::INTEGER AS draws,
    SUM(CASE WHEN mp.final_ranking > 1 THEN 1 ELSE 0 END)::INTEGER AS losses
FROM match_participants mp
JOIN matches m ON m.match_id = mp.match_id AND m.status = 'completed'
LEFT JOIN (
    SELECT match_id, COUNT(*)::INTEGER AS rank1_count
    FROM match_participants
    WHERE final_ranking = 1
    GROUP BY match_id
) r1 ON r1.match_id = mp.match_id
GROUP BY mp.user_id, m.game_id;

COMMENT ON VIEW v_match_outcomes IS 'Aggregated win/loss/draw totals derived from final_ranking and ties';


-- ============================================================================
-- VIEW: v_active_leaderboard
-- Active leaderboard with win rates and conservative ratings
-- ============================================================================
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
WHERE ugr.matches_played >= 5  -- Minimum matches for ranking
AND u.is_active = TRUE
AND g.is_active = TRUE
ORDER BY ugr.game_id, conservative_rating DESC;

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

COMMENT ON VIEW v_player_stats IS 'Comprehensive player statistics with rating trends';


-- ============================================================================
-- VIEW: v_global_leaderboard
-- Global cross-guild leaderboard
-- ============================================================================
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
  AND ugr.matches_played >= 10  -- Minimum for global ranking
ORDER BY ugr.game_id, conservative_rating DESC;

COMMENT ON VIEW v_global_leaderboard IS 'Global leaderboard (same data as user_game_ratings)';


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
    COALESCE(MAX(mc.cnt), 0)::BIGINT as move_count
FROM matches m
JOIN games g ON m.game_id = g.game_id
LEFT JOIN (
    SELECT match_id, COUNT(*)::BIGINT AS cnt
    FROM match_moves
    GROUP BY match_id
) mc ON mc.match_id = m.match_id
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
        WHEN mp.final_ranking = 1 AND COALESCE(r1.rank1_count, 0) > 1 THEN 'draw'
        WHEN mp.final_ranking = 1 THEN 'win'
        WHEN mp.final_ranking > 1 THEN 'loss'
        ELSE 'unknown'
    END as outcome,
    COUNT(*) OVER (
        PARTITION BY mp.user_id, m.game_id 
        ORDER BY m.ended_at
    ) as game_sequence_number
FROM match_participants mp
JOIN matches m ON mp.match_id = m.match_id
JOIN users u ON mp.user_id = u.user_id
JOIN games g ON m.game_id = g.game_id
LEFT JOIN (
    SELECT match_id, COUNT(*)::INTEGER AS rank1_count
    FROM match_participants
    WHERE final_ranking = 1
    GROUP BY match_id
) r1 ON r1.match_id = m.match_id
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
    COUNT(DISTINCT mp.user_id) as total_players,
    COUNT(DISTINCT m.game_id) as games_played,
    COUNT(DISTINCT m.match_id) FILTER (WHERE m.status = 'completed') as total_matches,
    MAX(m.ended_at) as last_activity,
    EXTRACT(EPOCH FROM (NOW() - MAX(m.ended_at)))::INTEGER / 86400 as days_since_activity,
    COUNT(DISTINCT CASE WHEN m.ended_at > NOW() - INTERVAL '7 days' THEN mp.user_id END) as active_players_7d,
    COUNT(DISTINCT CASE WHEN m.ended_at > NOW() - INTERVAL '30 days' THEN mp.user_id END) as active_players_30d
FROM guilds g
LEFT JOIN matches m ON m.guild_id = g.guild_id AND m.status = 'completed'
LEFT JOIN match_participants mp ON mp.match_id = m.match_id
GROUP BY g.guild_id, g.is_active
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

COMMENT ON VIEW v_game_popularity IS 'Game popularity and engagement metrics';