# Database Decisions

## Clean-slate baseline
The prerelease migration chain is retired.

- `schema.sql` is the authoritative baseline.
- `database_migrations` starts at `1.0.0`.
- Deploys are expected to recreate the database rather than replay historical prerelease migrations.

## Game registry authority
`games` is code-synchronized, not SQL-seeded.

- Shipped SQL does not insert default games.
- The plugin registry in `playcord/games/` is the source of truth for game availability and metadata.
- Schema rows are regenerated from plugin metadata during startup.

## Match state storage
Match completion and interruption data lives in `matches.metadata`.

- `matches.final_state` was removed.
- interruption details are stored in `metadata.reason`.
- optional end-state snapshots can be stored in `metadata.final_state`.

## Move and replay split
Gameplay audit and replay rendering remain separate concerns.

- `match_moves` stores ordered gameplay/system/reset steps used by the runtime.
- `replay_events` stores the broader replay/event stream, including stochastic or presentation-level events.

## Runtime-owned Discord messages
Bot-owned message rows are no longer persisted in SQL.

- Runtime tracks active owned-message references in memory while a match is running.
- Post-match and durable history lives in `replay_events` / `match_moves`, not message-row storage.

## Rating model
Ratings stay global per game.

- The rating identity remains `(user_id, game_id)`.
- Casual/custom options belong in `matches.game_config`.
- Materially different rated variants should register as distinct game keys instead of adding another leaderboard dimension.

## Analytics event taxonomy
Analytics event names are normalized through `analytics_event_types`.

- The runtime should emit known event types only.
- New event names should be added to the taxonomy before they are written from application code.
# Database Decisions

## Replay storage

PlayCord now uses `replay_events` as the single canonical replay store.

- `moves` remains the structured move-history table for gameplay/audit data.
- `replay_events` stores the viewer-facing event stream, including stochastic/system events.
- `matches.replay_log` is treated as legacy data only and is backfilled during migration.

`replay_events` shape:

- `match_id`: parent match
- `sequence_number`: stable per-match ordering
- `event_type`: discriminator such as `move`, `deck_shuffle`, or `rng_draw`
- `actor_user_id`: nullable actor for user/system/RNG events
- `payload`: JSONB event body

## TrueSkill authority

Runtime TrueSkill values come from `games.rating_config`.

- Code-defined defaults only seed the registry during `sync_games_from_code()`.
- Runtime reads should use `playcord.infrastructure.runtime_config.get_settings()` (and `playcord.state` for in-memory session maps), not duplicate globals.
- Per-game overrides still live on the game class via `trueskill_scale`, but they are folded into the seeded DB row.

## Preset / variant leaderboard strategy

Preset variants are modeled as separate `games` rows instead of adding a `preset_id` dimension.

- Rated presets with materially different rules should register as distinct game keys such as `chess_blitz`.
- Casual/custom one-off options stay in `matches.game_config` and should generally remain unrated.
- This keeps the rating key as `(user_id, game_id)` and avoids expanding every leaderboard/history query to include `preset_id`.
