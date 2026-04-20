# PlayCord Database

## Overview
PlayCord now treats the database as a clean-slate `1.0.0` baseline. The schema is driven by the current runtime and plugin model, not by historical prerelease game rows or migrations.

Startup flow:

- `schema.sql` creates the baseline schema and inserts the `1.0.0` migration marker.
- `functions.sql` and `views.sql` are reloaded on startup by `Database.refresh_sql_assets()`.
- `Database.sync_games_from_code()` populates `games` from the Python plugin registry.
- No shipped SQL file inserts default game rows anymore.

## Core tables
`guilds`

- One row per Discord guild.
- Stores guild-scoped settings in `settings`.

`users`

- One row per Discord user or synthetic bot player.
- Stores user preferences and activity flags.

`games`

- Registry of game plugins currently exposed by the app.
- Starts empty in SQL and is filled from code at startup.
- Holds `rating_config`, `game_metadata`, and the player-count envelope for each plugin.

`user_game_ratings`

- Global per-user, per-game TrueSkill ratings.
- Primary key shape is effectively `(user_id, game_id)` via a unique constraint.

`matches`

- One row per match lifecycle.
- `status` is a PostgreSQL `match_status` enum: `in_progress`, `completed`, `abandoned`, `interrupted`.
- `game_config` stores match options used for that run.
- `metadata` stores structured runtime data such as interruption reasons and stored summaries.
- `final_state` is no longer a dedicated column; end-of-match snapshots live in `metadata.final_state` if needed.

`match_participants`

- One row per user in a match.
- Stores seat order, final ranking, and rating deltas.

`match_moves`

- Canonical move log for gameplay and audit.
- Replaces the old `moves` table.
- Adds `kind` so the runtime can distinguish regular moves from system/reset records.

`replay_events`

- Viewer-facing replay/event stream.
- Stores ordered structured events, including non-move runtime events.

`analytics_event_types`

- Taxonomy of allowed analytics event names.
- `analytics_events.event_type` references this table.

`analytics_events`

- Append-only analytics log keyed by event type plus optional user/guild/game/match foreign keys.

`rating_history`

- Historical rating transitions written when rated matches complete.

`database_migrations`

- Tracks applied SQL migrations.
- Reset to a single clean-slate baseline version, `1.0.0`.

## SQL helpers
Important functions:

- `apply_skill_decay()`: raises uncertainty for inactive ratings.
- `validate_move_sequence()`: now requires numbering to start at `1`, not just be gap-free.
- `get_player_activity_summary()`: draw counting now treats tied rank-1 finishes as draws.
- `sync_games_played_counts()`: repair helper for `matches_played`.

Important views:

- `v_match_outcomes`
- `v_active_leaderboard`
- `v_player_stats`
- `v_match_summary`
- `v_user_match_history`

`v_player_stats.is_uncertain` was removed because the old heuristic was not authoritative enough to keep in the schema.

## Runtime expectations
The new game runtime assumes:

- `games` is synchronized from plugin metadata, not seeded SQL.
- `match_moves` is the authoritative move-history table.
- interruption reasons are written to `matches.metadata.reason`.
- replay/event data uses `replay_events`, not legacy text logs.

## Resetting locally
For a full local reset, use the app/database reset path that rebuilds the public schema from tracked assets. Do not try to replay old prerelease migrations; the supported baseline is the current `1.0.0` schema only.
