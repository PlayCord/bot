-- PlayCord PostgreSQL Database Schema
-- Version: 1.0.0
-- Description: Comprehensive database schema for Discord game bot with TrueSkill rating system
--
-- Key Features:
-- - Global per-game rating tracking
-- - Match move, replay, and bot-owned message history
-- - Analytics event taxonomy
-- - Plugin-driven game registry with no seeded default games

-- Drop existing database if exists (development only)
-- Uncomment for fresh start: DROP DATABASE IF EXISTS playcord;

-- Create database (run manually if needed)
-- CREATE DATABASE playcord WITH ENCODING 'UTF8' LC_COLLATE='en_US.UTF-8' LC_CTYPE='en_US.UTF-8';

CREATE TYPE match_status AS ENUM (
    'in_progress',
    'completed',
    'abandoned',
    'interrupted'
);

-- ============================================================================
-- TABLE: guilds
-- Discord servers/guilds where the bot is installed
-- ============================================================================
CREATE TABLE IF NOT EXISTS guilds
(
    guild_id   BIGINT PRIMARY KEY,
    settings   JSONB       DEFAULT '{}'::jsonb,
    is_active  BOOLEAN     DEFAULT TRUE  NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Index for active guilds
CREATE INDEX IF NOT EXISTS idx_guilds_active ON guilds (is_active, created_at DESC);

COMMENT ON TABLE guilds IS 'Discord servers where PlayCord is installed';
COMMENT ON COLUMN guilds.settings IS 'Guild preferences: {"default_game": "tictactoe", "leaderboard_public": true, ...}';


-- ============================================================================
-- TABLE: users
-- Discord users who have interacted with the bot
-- ============================================================================
CREATE TABLE IF NOT EXISTS users
(
    user_id     BIGINT PRIMARY KEY,
    username    VARCHAR(100)              NOT NULL,
    preferences JSONB       DEFAULT '{}'::jsonb,
    is_bot      BOOLEAN     DEFAULT FALSE NOT NULL,
    is_active   BOOLEAN     DEFAULT TRUE  NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at  TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    CONSTRAINT chk_username_not_empty CHECK (LENGTH(TRIM(username)) > 0)
);

-- Index for active users and username searches
CREATE INDEX IF NOT EXISTS idx_users_active ON users (is_active, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_users_username ON users (username varchar_pattern_ops);

COMMENT ON TABLE users IS 'Discord users who have interacted with PlayCord';
COMMENT ON COLUMN users.username IS 'Cached Discord username for queries (updated periodically)';
COMMENT ON COLUMN users.preferences IS 'User preferences: {"favorite_game": "chess", "notifications": true, ...}';


-- ============================================================================
-- TABLE: games
-- Registry of available games with their configurations
-- ============================================================================
CREATE TABLE IF NOT EXISTS games
(
    game_id             SERIAL PRIMARY KEY,
    game_name           VARCHAR(100) UNIQUE       NOT NULL,
    display_name        VARCHAR(200)              NOT NULL,
    min_players         INTEGER                   NOT NULL,
    max_players         INTEGER                   NOT NULL,
    rating_config       JSONB                     NOT NULL,
    game_metadata       JSONB       DEFAULT '{}'::jsonb,
    game_schema_version INTEGER     DEFAULT 1     NOT NULL,
    is_active           BOOLEAN     DEFAULT TRUE  NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at          TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    CONSTRAINT chk_game_players CHECK (min_players >= 1 AND max_players >= min_players),
    CONSTRAINT chk_game_name_format CHECK (game_name ~ '^[a-z][a-z0-9_]*$'),
    CONSTRAINT chk_rating_config_keys CHECK (
        rating_config ? 'sigma' AND
        rating_config ? 'beta' AND
        rating_config ? 'tau' AND
        rating_config ? 'draw'
        )
);

-- Index for active games
CREATE INDEX IF NOT EXISTS idx_games_active ON games (is_active, game_name);

COMMENT ON TABLE games IS 'Registry of available games and their TrueSkill configurations';
COMMENT ON COLUMN games.game_name IS 'Internal game identifier (lowercase, snake_case)';
COMMENT ON COLUMN games.display_name IS 'Human-readable game name for display';
COMMENT ON COLUMN games.rating_config IS 'TrueSkill parameters: {"sigma": 0.1667, "beta": 0.0833, "tau": 0.01, "draw": 0.9}';
COMMENT ON COLUMN games.game_metadata IS 'Game rules, description, etc.: {"description": "...", "rules": [...], ...}';
COMMENT ON COLUMN games.game_schema_version IS 'Bumped when game definition in code changes; used for registration sync';


-- ============================================================================
-- TABLE: user_game_ratings
-- One TrueSkill rating per user per game (global); guild leaderboards filter by member list in app/SQL
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_game_ratings
(
    rating_id           BIGSERIAL PRIMARY KEY,
    user_id             BIGINT                    NOT NULL,
    game_id             INTEGER                   NOT NULL,
    mu                  DOUBLE PRECISION          NOT NULL DEFAULT 1000.0,
    sigma               DOUBLE PRECISION          NOT NULL DEFAULT 333.33,
    matches_played      INTEGER     DEFAULT 0     NOT NULL,
    last_played         TIMESTAMPTZ,
    last_sigma_increase TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at          TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    CONSTRAINT uq_user_game UNIQUE (user_id, game_id),
    CONSTRAINT fk_user_rating_user FOREIGN KEY (user_id)
        REFERENCES users (user_id) ON DELETE CASCADE,
    CONSTRAINT fk_user_rating_game FOREIGN KEY (game_id)
        REFERENCES games (game_id) ON DELETE CASCADE,
    CONSTRAINT chk_rating_floor CHECK (mu >= 0.0 AND sigma >= 0.001),
    CONSTRAINT chk_matches_counts CHECK (matches_played >= 0)
);

-- Indexes for leaderboard queries and user activity
CREATE INDEX IF NOT EXISTS idx_rating_leaderboard ON user_game_ratings (
                                                                        game_id, (mu - 3 * sigma) DESC
    ) WHERE matches_played >= 5;

CREATE INDEX IF NOT EXISTS idx_rating_user_activity ON user_game_ratings (
                                                                          user_id, game_id, last_played DESC
    );

CREATE INDEX IF NOT EXISTS idx_rating_inactive ON user_game_ratings (last_played)
    WHERE last_played IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_rating_game ON user_game_ratings (game_id);

-- Guild leaderboard queries: filter by game_id then member user_ids
CREATE INDEX IF NOT EXISTS idx_rating_game_user ON user_game_ratings (game_id, user_id);

COMMENT ON TABLE user_game_ratings IS 'TrueSkill ratings: one row per user per game (not per guild)';
COMMENT ON COLUMN user_game_ratings.mu IS 'TrueSkill mean (skill estimate)';
COMMENT ON COLUMN user_game_ratings.sigma IS 'TrueSkill standard deviation (uncertainty)';
COMMENT ON COLUMN user_game_ratings.last_sigma_increase IS 'When sigma was last increased due to inactivity (skill decay)';


-- ============================================================================
-- TABLE: matches
-- Completed and in-progress game matches
-- ============================================================================
CREATE TABLE IF NOT EXISTS matches
(
    match_id    BIGSERIAL PRIMARY KEY,
    game_id     INTEGER                           NOT NULL,
    guild_id    BIGINT                            NOT NULL,
    channel_id  BIGINT                            NOT NULL,
    thread_id   BIGINT,
    started_at  TIMESTAMPTZ DEFAULT NOW()         NOT NULL,
    ended_at    TIMESTAMPTZ,
    status      match_status DEFAULT 'in_progress' NOT NULL,
    is_rated    BOOLEAN     DEFAULT TRUE          NOT NULL,
    game_config JSONB       DEFAULT '{}'::jsonb,
    match_code  VARCHAR(8),
    metadata    JSONB       DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ DEFAULT NOW()         NOT NULL,
    updated_at  TIMESTAMPTZ DEFAULT NOW()         NOT NULL,

    CONSTRAINT fk_match_game FOREIGN KEY (game_id)
        REFERENCES games (game_id) ON DELETE CASCADE,
    CONSTRAINT fk_match_guild FOREIGN KEY (guild_id)
        REFERENCES guilds (guild_id) ON DELETE CASCADE,
    CONSTRAINT chk_match_end_time CHECK (
        ended_at IS NULL OR ended_at > started_at
        )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_matches_match_code ON matches (match_code)
    WHERE match_code IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_matches_match_code_ci ON matches ((lower(match_code)))
    WHERE match_code IS NOT NULL;

-- Indexes for match queries
CREATE INDEX IF NOT EXISTS idx_matches_guild_game ON matches (
                                                              guild_id, game_id, ended_at DESC NULLS LAST
    );

CREATE INDEX IF NOT EXISTS idx_matches_status ON matches (
                                                          status, started_at DESC
    ) WHERE status = 'in_progress';

CREATE INDEX IF NOT EXISTS idx_matches_recent ON matches (ended_at DESC)
    WHERE ended_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_matches_channel ON matches (channel_id, status);

COMMENT ON TABLE matches IS 'Game matches (completed and in-progress)';
COMMENT ON COLUMN matches.game_config IS 'Game-specific settings used for this match';
COMMENT ON COLUMN matches.metadata IS 'Structured metadata including reason payloads such as {"reason": {"type": "error", "exception": "...", "detail": "..."}}';


-- ============================================================================
-- TABLE: match_participants
-- Players in each match with their results
-- ============================================================================
CREATE TABLE IF NOT EXISTS match_participants
(
    participant_id BIGSERIAL PRIMARY KEY,
    match_id       BIGINT                         NOT NULL,
    user_id        BIGINT                         NOT NULL,
    player_number  INTEGER                        NOT NULL,
    final_ranking  INTEGER,
    score          DOUBLE PRECISION,
    mu_before      DOUBLE PRECISION,
    sigma_before   DOUBLE PRECISION,
    mu_delta       DOUBLE PRECISION DEFAULT 0.0   NOT NULL,
    sigma_delta    DOUBLE PRECISION DEFAULT 0.0   NOT NULL,
    joined_at      TIMESTAMPTZ      DEFAULT NOW() NOT NULL,
    updated_at     TIMESTAMPTZ      DEFAULT NOW() NOT NULL,

    CONSTRAINT uq_match_user UNIQUE (match_id, user_id),
    CONSTRAINT uq_match_player_number UNIQUE (match_id, player_number),
    CONSTRAINT fk_participant_match FOREIGN KEY (match_id)
        REFERENCES matches (match_id) ON DELETE CASCADE,
    CONSTRAINT fk_participant_user FOREIGN KEY (user_id)
        REFERENCES users (user_id) ON DELETE CASCADE,
    CONSTRAINT chk_player_number CHECK (player_number >= 1),
    CONSTRAINT chk_final_ranking CHECK (final_ranking IS NULL OR final_ranking >= 1)
);

-- Indexes for participant queries
CREATE INDEX IF NOT EXISTS idx_participants_match ON match_participants (match_id, player_number);
CREATE INDEX IF NOT EXISTS idx_participants_user ON match_participants (user_id, match_id DESC);
CREATE INDEX IF NOT EXISTS idx_participants_ranking ON match_participants (match_id, final_ranking);

COMMENT ON TABLE match_participants IS 'Players in each match with rankings and rating changes';
COMMENT ON COLUMN match_participants.player_number IS 'Turn order in the game (1-indexed)';
COMMENT ON COLUMN match_participants.final_ranking IS '1 = winner, higher = worse; ties allowed via same ranking';
COMMENT ON COLUMN match_participants.score IS 'Optional numeric score for the participant';
COMMENT ON COLUMN match_participants.mu_before IS 'Rating before this match (for history)';
COMMENT ON COLUMN match_participants.sigma_before IS 'Uncertainty before this match (for history)';


-- ============================================================================
-- TABLE: match_moves
-- Full move history for game replay and audit
-- ============================================================================
CREATE TABLE IF NOT EXISTS match_moves
(
    move_id          BIGSERIAL PRIMARY KEY,
    match_id         BIGINT                    NOT NULL,
    user_id          BIGINT,
    move_number      INTEGER                   NOT NULL,
    kind             VARCHAR(20) DEFAULT 'move' NOT NULL,
    move_data        JSONB                     NOT NULL,
    game_state_after JSONB,
    is_game_affecting BOOLEAN     DEFAULT TRUE  NOT NULL,
    created_at       TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    time_taken_ms    INTEGER,

    CONSTRAINT chk_match_move_kind CHECK (kind IN ('move', 'system', 'reset')),
    CONSTRAINT uq_match_move_number UNIQUE (match_id, move_number),
    CONSTRAINT fk_move_match FOREIGN KEY (match_id)
        REFERENCES matches (match_id) ON DELETE CASCADE,
    CONSTRAINT fk_move_user FOREIGN KEY (user_id)
        REFERENCES users (user_id) ON DELETE CASCADE,
    CONSTRAINT chk_move_number CHECK (move_number >= 1),
    CONSTRAINT chk_time_taken CHECK (time_taken_ms IS NULL OR time_taken_ms >= 0)
);

-- Index for sequential move replay
CREATE INDEX IF NOT EXISTS idx_match_moves_match_sequence ON match_moves (match_id, move_number ASC);
CREATE INDEX IF NOT EXISTS idx_match_moves_user ON match_moves (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_match_moves_created_at ON match_moves (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_match_moves_game_affecting ON match_moves (is_game_affecting)
    WHERE is_game_affecting = TRUE;

COMMENT ON TABLE match_moves IS 'Complete move history for game replay and auditing';
COMMENT ON COLUMN match_moves.user_id IS 'Player who made the move (NULL for system/automatic moves)';
COMMENT ON COLUMN match_moves.kind IS 'move, system, or reset';
COMMENT ON COLUMN match_moves.move_data IS 'Game-specific move format: {"position": "e4", "piece": "pawn", ...}';
COMMENT ON COLUMN match_moves.game_state_after IS 'Optional: Full game state after this move for replay';
COMMENT ON COLUMN match_moves.time_taken_ms IS 'Thinking time in milliseconds';
COMMENT ON COLUMN match_moves.is_game_affecting IS 'False for cosmetic/no-op moves excluded from replay logic';


-- ============================================================================
-- TABLE: analytics_event_types
-- Known analytics event type taxonomy
-- ============================================================================
CREATE TABLE IF NOT EXISTS analytics_event_types
(
    event_type  VARCHAR(100) PRIMARY KEY,
    description TEXT,
    is_active   BOOLEAN     DEFAULT TRUE  NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

COMMENT ON TABLE analytics_event_types IS 'Known analytics event names used by PlayCord';

INSERT INTO analytics_event_types (event_type, description)
VALUES
    ('bot_started', 'Bot process booted successfully'),
    ('command_used', 'A slash command or move command was executed'),
    ('error_occurred', 'An unexpected runtime or infrastructure error occurred'),
    ('game_abandoned', 'A match was abandoned before completion'),
    ('game_completed', 'A match reached a completed outcome'),
    ('game_interrupted', 'A match was interrupted before completion'),
    ('game_started', 'A new match runtime was started'),
    ('guild_joined', 'Bot joined a guild'),
    ('guild_left', 'Bot left a guild'),
    ('matchmaking_joined', 'A player joined a matchmaking lobby'),
    ('matchmaking_left', 'A player left a matchmaking lobby'),
    ('matchmaking_matched', 'A lobby transitioned into an active match'),
    ('matchmaking_started', 'A matchmaking lobby was created'),
    ('matchmaking_completed', 'A matchmaking lobby completed successfully'),
    ('matchmaking_cancelled', 'A matchmaking lobby ended without a game'),
    ('player_joined', 'A player joined a match'),
    ('player_left', 'A player left a match'),
    ('move_made', 'A match move or equivalent interaction was applied'),
    ('move_valid', 'A move was accepted'),
    ('move_invalid', 'A move was rejected as invalid'),
    ('move_rejected', 'A move could not be routed or executed'),
    ('rating_updated', 'A player rating row changed'),
    ('skill_decay_applied', 'Inactivity-based sigma decay was applied')
ON CONFLICT (event_type) DO UPDATE SET
    description = EXCLUDED.description;


-- ============================================================================
-- TABLE: analytics_events
-- Event tracking for analytics and monitoring
-- ============================================================================
CREATE TABLE IF NOT EXISTS analytics_events
(
    event_id   BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(100)              NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    user_id    BIGINT,
    guild_id   BIGINT,
    game_id    INTEGER,
    match_id   BIGINT,
    metadata   JSONB       DEFAULT '{}'::jsonb,

    CONSTRAINT fk_event_type FOREIGN KEY (event_type)
        REFERENCES analytics_event_types (event_type) ON DELETE RESTRICT,
    CONSTRAINT fk_event_user FOREIGN KEY (user_id)
        REFERENCES users (user_id) ON DELETE SET NULL,
    CONSTRAINT fk_event_guild FOREIGN KEY (guild_id)
        REFERENCES guilds (guild_id) ON DELETE SET NULL,
    CONSTRAINT fk_event_game FOREIGN KEY (game_id)
        REFERENCES games (game_id) ON DELETE SET NULL,
    CONSTRAINT fk_event_match FOREIGN KEY (match_id)
        REFERENCES matches (match_id) ON DELETE SET NULL
);

-- Indexes for analytics queries
CREATE INDEX IF NOT EXISTS idx_analytics_type_time ON analytics_events (event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_user ON analytics_events (user_id, created_at DESC)
    WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_analytics_guild ON analytics_events (guild_id, created_at DESC)
    WHERE guild_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_analytics_created_at ON analytics_events (created_at DESC);

COMMENT ON TABLE analytics_events IS 'Event tracking for analytics and monitoring';
COMMENT ON COLUMN analytics_events.event_type IS 'Event types: game_started, game_completed, matchmaking_*, etc.';
COMMENT ON COLUMN analytics_events.metadata IS 'Event-specific data: {"duration_seconds": 120, "error": "...", ...}';


-- ============================================================================
-- TABLE: rating_history
-- Historical rating changes for tracking progress over time
-- ============================================================================
CREATE TABLE IF NOT EXISTS rating_history
(
    history_id   BIGSERIAL PRIMARY KEY,
    user_id      BIGINT                    NOT NULL,
    guild_id     BIGINT,
    game_id      INTEGER                   NOT NULL,
    match_id     BIGINT                    NOT NULL,
    mu_before    DOUBLE PRECISION          NOT NULL,
    sigma_before DOUBLE PRECISION          NOT NULL,
    mu_after     DOUBLE PRECISION          NOT NULL,
    sigma_after  DOUBLE PRECISION          NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    CONSTRAINT fk_history_user FOREIGN KEY (user_id)
        REFERENCES users (user_id) ON DELETE CASCADE,
    CONSTRAINT fk_history_guild FOREIGN KEY (guild_id)
        REFERENCES guilds (guild_id) ON DELETE SET NULL,
    CONSTRAINT fk_history_game FOREIGN KEY (game_id)
        REFERENCES games (game_id) ON DELETE CASCADE,
    CONSTRAINT fk_history_match FOREIGN KEY (match_id)
        REFERENCES matches (match_id) ON DELETE CASCADE
);

-- Indexes for rating history queries
CREATE INDEX IF NOT EXISTS idx_history_user_game ON rating_history (
                                                                    user_id, game_id, created_at DESC
    );
CREATE INDEX IF NOT EXISTS idx_history_match ON rating_history (match_id);
CREATE INDEX IF NOT EXISTS idx_history_guild_game ON rating_history (
                                                                     guild_id, game_id, created_at DESC
    );

COMMENT ON TABLE rating_history IS 'Historical rating changes for progress tracking';


-- ============================================================================
-- TABLE: replay_events
-- Structured replay / RNG event log (canonical replay storage)
-- ============================================================================
CREATE TABLE IF NOT EXISTS replay_events
(
    event_id         BIGSERIAL PRIMARY KEY,
    match_id         BIGINT                    NOT NULL,
    sequence_number  INTEGER                   NOT NULL,
    event_type       VARCHAR(100)              NOT NULL,
    actor_user_id    BIGINT,
    payload          JSONB       DEFAULT '{}'::jsonb NOT NULL,
    created_at       TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    CONSTRAINT fk_replay_match FOREIGN KEY (match_id)
        REFERENCES matches (match_id) ON DELETE CASCADE,
    CONSTRAINT fk_replay_actor FOREIGN KEY (actor_user_id)
        REFERENCES users (user_id) ON DELETE SET NULL,
    CONSTRAINT uq_replay_sequence UNIQUE (match_id, sequence_number),
    CONSTRAINT chk_replay_sequence CHECK (sequence_number >= 1)
);

CREATE INDEX IF NOT EXISTS idx_replay_match_sequence ON replay_events (match_id, sequence_number ASC);
CREATE INDEX IF NOT EXISTS idx_replay_actor ON replay_events (actor_user_id, created_at DESC)
    WHERE actor_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_replay_type ON replay_events (event_type, created_at DESC);

COMMENT ON TABLE replay_events IS 'Canonical structured replay log, including moves and stochastic/system events';
COMMENT ON COLUMN replay_events.payload IS 'Arbitrary replay event payload. event_type carries the stable discriminator.';


-- ============================================================================
-- TABLE: bot_messages
-- Track every message owned by the bot runtime for a match
-- ============================================================================
CREATE TABLE IF NOT EXISTS bot_messages
(
    bot_message_id     BIGSERIAL PRIMARY KEY,
    match_id           BIGINT                    NOT NULL,
    discord_message_id BIGINT                    NOT NULL,
    channel_id         BIGINT                    NOT NULL,
    message_key        VARCHAR(100)              NOT NULL,
    purpose            VARCHAR(32)               NOT NULL,
    payload_digest     VARCHAR(64),
    metadata           JSONB       DEFAULT '{}'::jsonb NOT NULL,
    deleted_at         TIMESTAMPTZ,
    created_at         TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at         TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    CONSTRAINT fk_bot_messages_match FOREIGN KEY (match_id)
        REFERENCES matches (match_id) ON DELETE CASCADE,
    CONSTRAINT uq_bot_messages_discord_id UNIQUE (discord_message_id),
    CONSTRAINT uq_bot_messages_key UNIQUE (match_id, message_key),
    CONSTRAINT chk_bot_message_purpose CHECK (
        purpose IN ('board', 'announcement', 'ephemeral', 'turn_notification', 'custom', 'overview')
    )
);

CREATE INDEX IF NOT EXISTS idx_bot_messages_match ON bot_messages (match_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_bot_messages_purpose ON bot_messages (match_id, purpose, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_bot_messages_channel ON bot_messages (channel_id, created_at DESC);

COMMENT ON TABLE bot_messages IS 'Messages owned by the runtime for a match';
COMMENT ON COLUMN bot_messages.message_key IS 'Stable key such as board, status, or turn_notice';
COMMENT ON COLUMN bot_messages.metadata IS 'Runtime metadata, including summaries and lookup hints';


-- ============================================================================
-- TABLE: database_migrations
-- Track applied database migrations for version control
-- ============================================================================
CREATE TABLE IF NOT EXISTS database_migrations
(
    migration_id SERIAL PRIMARY KEY,
    version      VARCHAR(50) UNIQUE        NOT NULL,
    description  TEXT,
    applied_at   TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    checksum     VARCHAR(64),

    CONSTRAINT chk_version_format CHECK (version ~ '^\d+\.\d+(\.\d+)?$')
);

COMMENT ON TABLE database_migrations IS 'Track database schema versions and migrations';
COMMENT ON COLUMN database_migrations.checksum IS 'SHA-256 checksum of migration file for verification';


-- ============================================================================
-- TRIGGERS
-- Automatic updates for timestamp columns
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS
$$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply update_updated_at trigger to relevant tables
CREATE TRIGGER tr_guilds_updated_at
    BEFORE UPDATE
    ON guilds
    FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER tr_users_updated_at
    BEFORE UPDATE
    ON users
    FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER tr_games_updated_at
    BEFORE UPDATE
    ON games
    FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER tr_ratings_updated_at
    BEFORE UPDATE
    ON user_game_ratings
    FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER tr_matches_updated_at
    BEFORE UPDATE
    ON matches
    FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER tr_match_participants_updated_at
    BEFORE UPDATE
    ON match_participants
    FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER tr_bot_messages_updated_at
    BEFORE UPDATE
    ON bot_messages
    FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();


-- ============================================================================
-- INITIAL MIGRATION RECORD
-- ============================================================================
INSERT INTO database_migrations (version, description)
VALUES (
    '1.0.0',
    'Clean-slate schema: plugin registry, match_status enum, match_moves, bot_messages'
)
ON CONFLICT (version) DO NOTHING;

