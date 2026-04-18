-- PlayCord Database Seed Data
-- Version: 1.0.0
--
-- This file intentionally does not insert games. The `games` table is now
-- populated exclusively from the Python plugin registry during startup.

INSERT INTO analytics_event_types (event_type, description)
VALUES
    ('bot_started', 'Bot process booted successfully'),
    ('command_used', 'A slash command or move command was executed'),
    ('error_occurred', 'An unexpected runtime or infrastructure error occurred'),
    ('game_completed', 'A match reached a completed outcome'),
    ('game_interrupted', 'A match was interrupted before completion'),
    ('game_started', 'A new match runtime was started'),
    ('guild_joined', 'Bot joined a guild'),
    ('guild_left', 'Bot left a guild'),
    ('matchmaking_joined', 'A player joined a matchmaking lobby'),
    ('matchmaking_left', 'A player left a matchmaking lobby'),
    ('matchmaking_matched', 'A lobby transitioned into an active match'),
    ('move_made', 'A match move or equivalent interaction was applied'),
    ('rating_updated', 'A player rating row changed'),
    ('skill_decay_applied', 'Inactivity-based sigma decay was applied')
ON CONFLICT (event_type) DO UPDATE SET
    description = EXCLUDED.description;
