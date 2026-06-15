-- PlayCord Database Views
-- Common query patterns as views for performance

-- ============================================================================
-- VIEW: v_match_outcomes
-- Shared win/loss/draw aggregation used by stats views
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
            'final_ranking', mp.final_ranking
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
    mp.player_number,
    mp.final_ranking,
    mp.score,
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

COMMENT ON VIEW v_user_match_history IS 'User match history with outcomes';


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
    MAX(m.ended_at) as last_played
FROM games gm
LEFT JOIN matches m ON m.game_id = gm.game_id AND m.status = 'completed'
LEFT JOIN match_participants mp ON mp.match_id = m.match_id
WHERE gm.is_active = TRUE
GROUP BY gm.game_id, gm.game_name, gm.display_name
ORDER BY total_matches DESC NULLS LAST;

COMMENT ON VIEW v_game_popularity IS 'Game popularity and engagement metrics';
