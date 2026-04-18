# [BROKEN.md](http://BROKEN.md)

The idea of this file is to store everything known to be broken, as well as the new features I want to add. When this is
empty, I will release 1.0.0

Note: the 2026 internal architecture refactor (typed `playcord/` package, programmatic command tree, DI container,
tooling/CI, and shared UI/error primitives) is now tracked in code rather than in this backlog file. Items below are
product-facing follow-up work that still remains.

## Features (focus on this)

- No match replay functionality (viewer / sharing)
  - **Done (persistence):** After a callback, `GameInterface` calls `Database.record_move` and `append_replay_event`
  (JSONL on `matches.replay_log`) only when `[_should_persist_move_replay](utils/interfaces.py)` allows it: for
  game-affecting commands, `**return None`** (move applied) or `**Response(..., record_replay=True)**` (applied but
  still returning a message); plain `**Response**` without that flag = validation/no-op → **not** logged. Commands
  with `**is_game_affecting=False`** (e.g. Poker/Blackjack `peek`) never log. Bot moves use bot `user_id`.
  - **RNG in replay:** `Game.attach_replay_logger` / `Game.log_replay_event` / `on_replay_logger_attached` for stochastic
  setup; Poker (deck + showdown tiebreak), Blackjack (each shuffle), No Thanks (setup), Battleship (placement), Liar's
  Dice (initial hands) log; per-die rerolls during play still not logged (optional).
  - **Done (viewer / discovery):** `/playcord replay <match_id>` (guild-only) shows paginated JSONL-derived lines via
  `[utils/replay_format.py](utils/replay_format.py)`. `/playcord history` rows prefix ``match_id`` so users can
  copy the ID.
  - **Still TODO:** Web or richer replay UI, ensuring every randomizing game logs stochastic outcomes, broader testing.
- We need a way to prevent people from sending messages in game thread that are not commands, or people spectating
from sending anything at all. The issue is that the app command and send message privileges are combined.
  - **Partial:** `THREAD_POLICY_PARTICIPANTS_COMMANDS_ONLY` in `playcord/infrastructure/app_constants.py` (default off) deletes
  non-`/` messages from **participants** in active game threads. Spectators are still non-participants (existing
  warn/delete policy applies); true “spectators silent” may need permission tweaks or stricter deletion.
- Better match history summaries (foundation)
  - **Done:** `Game.match_global_summary(outcome) -> str | None` (one line: result / scoreboard) and
  `match_summary` (per-player lines), stored as `metadata.outcome_global_summary` and `outcome_summaries`;
  global line is shown at the top of the game-over embed and replay viewer; per-player lines in history. Legacy
  `outcome_summary` string is still read for old history rows. Example:
  `[games/TicTacToe.py](games/TicTacToe.py)`.
  - **Partial:** `match_global_summary` + per-player `match_summary` on Chess, Poker, Connect Four, Reversi, Nim,
  Tic-Tac-Toe, Battleship, Blackjack Table, No Thanks, Mastermind Duel; other games can override both on
  `[api/Game.py](api/Game.py)` as needed.
- Better seating algorithm for games. Some games are asymmetric (like Mastermind) and seating can have a big impact
on the game, so we should take that into account when seating players.
  - We would need maybe a way to configure roles for players in each game, and then the seating algorithm would try to
  seat players in a way that balances those roles as much as possible. This would be a pretty complex feature but
  could add a lot of value for certain games. Sometimes it would benefit for this to be random (Secret Hitler), but
  other times we want it to be set. This is something that would be added to the API.
- Add a feedback command
  - **Done:** `/playcord feedback` records `user_feedback` analytics events with message text (see `[cogs/general.py](cogs/general.py)`).
- Add customization options for games (board size, wordlist, basically configurable things). This would probably be
within the matchmaker GUI and not a command (because we don't want to have a /play command for EVERY game
  - There are other questions raised by this:
  - How do we store this information?
  - How do we display it in the matchmaker?
  - How do we handle leaderboards? is there a specified "correct ruleset", or can there be multiple presets? There
  might be several different ways to play a game, and we want that to all be contained within the single game
  instance.
  - This also opens up the possibility of players creating their own custom games by defining the ruleset in a config
  file or something, and then the bot just implements the mechanics of running the game and enforcing the ruleset.
  This is a much more complex feature but could be really cool. Would also force unrated obviously.
- Rematch button after games
  - **Done:** `RematchView` on the overview message; `[GamesCog.rematch_button_callback](cogs/games.py)` rebuilds a
  lobby with human participants via `[MatchmakingInterface.seed_rematch_players](utils/interfaces.py)`.
- Remove the made with love footer in most locations, except for about command etc
  - `[brand] footer` in locale may still be unused; `/about` uses copyright footer. **Checked:** production games do not
  use `Footer` for brand copy; only `[games/TestGame.py](games/TestGame.py)` includes a demo `Footer` for API examples.
- New custom emojis made for the bot
  - Pixel art, use the blue pixel art duotone
- Substitution emoji logic is really janky and should be redone, especially for custom emojis
  - **Partial:** `[get_emoji_string](utils/emojis.py)` now coerces emoji ids to int safely; deeper refactor (e.g.
  unified `parse_discord_emoji` path) still optional.
- Add a better way to limit the bot's scope (full product vision)
  - **Partial today:** Guild setting `playcord_channel_id` in `guilds.settings`; `/playcord set_channel` (admin);
  onboarding mentions it; `[playcord.require_playcord_channel](configuration/config.yaml)` forces `/play` to run
  only
  in that channel when true.
  - **Not done:** Matchmaker UI always posted into the bot channel while `/play` can start elsewhere; “everything
  requires channel if unset” beyond `/play` guard.
  - **Partial:** Active game thread title uses `[queue.thread_name](configuration/locale/en.toml)` (`match_id` + game
  label); further “PlayCord” / branding cleanup in thread names or copy still optional.
- Database problems (Phase 1 foundation — see below; broader schema for leaderboards / presets / replay UI still
evolves with other features)
  - FFA vs win/loss/tie: `match_participants` uses `final_ranking`; SQL helper
  `calculate_win_loss_tie_from_ranking` exists. **Denormalized `wins` / `losses` / `draws` were removed** from
  `user_game_ratings`; derive outcomes from `match_participants` (see `v_active_leaderboard` / `v_player_stats`).
  - Prevent negative ratings: `mu >= 0` (CHECK + trigger using `games.rating_config.min_mu` + config
  `ratings.min_mu`), plus Python clamps on rating updates.
  - Prevent sigma too small: `sigma >= 0.001` (CHECK + `min_sigma` in rating_config + config `ratings.min_sigma`),
  skill decay and global rating aggregation clamp to the floor.
  - Broader schema work still tied to leaderboards, customization, full replay pipeline, etc. (ongoing)
  - `matches_played` drift: `sync_games_played_counts()` recomputes from completed matches; runs on bot startup
  (best-effort if the function is missing on ancient DBs).
  - Game registration from code: `sync_games_from_code()` on startup upserts all `GAME_TYPES` entries;
  `games.game_schema_version` and `Game.game_schema_version` for tracking definition changes. **Not yet:** using DB
  state to auto-detect Discord command tree drift (see separate item below).
- Detect if the synced commands are not equal to the local command tree and auto sync
  - **Partial:** `[bot.auto_sync_commands](configuration/config.yaml)` runs a full `tree.sync()` on startup when true;
  no hash/compare of Discord vs local tree yet.
- Move the trueskill rating stuff INTO the game class (full modular swap)
  - **Partial:** `[Game.trueskill_scale](api/Game.py)` optional dict (`sigma`/`beta`/`tau`/`draw` as fractions of MU);
  `[game_over](utils/interfaces.py)` uses `trueskill_scale` with `GAME_TRUESKILL` fallback. Per-game DB
  `rating_config` still used for floors/sync elsewhere.
  - **Still TODO:** Single named API like `game.trueskill_parameters`, reading defaults from DB row in one place, drop
  duplication with `GAME_TRUESKILL` when every game defines scales.
- Error handling (broader coverage)
  - **Partial:** `[successful_matchmaking](utils/interfaces.py)` wrapped; failures edit the lobby message with an
  error embed + traceback (internal path). Other setup paths may still fail quietly.
  - If a crash occurs during game setup or something where it is *our* fault (not within a game's code), we still need
  to show an error consistently everywhere.
- Analytics viewer of some kind
  - **Partial:** Owner message command `[playcord/analytics [hours]](cogs/admin.py)` — aggregates by `event_type` plus
  recent rows (id, user, guild, match, metadata). Events are written **directly** to `analytics_events` from
  `[register_event](utils/analytics.py)` (matchmaking started, game started/completed/abandoned,
  feedback, etc.). Background flush retries buffered rows after failures. No charts UI yet.
- More modular game format
  - Currently all of the games have some kind of "game_message" that is entirely controlled by it (within parameters)
  - It might be good/cool to have a more open format where more messages are sent by the bot in the channel as the
  game progresses, maybe with occasional resets ETC.
  - This would also change the bot-provided current turn embed to an ephemeral notification sent by the bot (or a
  message)
  - This would greatly increase the number of possibilities for games.
  - If this was implemented, it would completely replace the current game infrastructure but have such a large
  featureset that implementing a game in the current method would also be trivial
- Pagination after bot restarts (UX)
  - **Done:** Pagination callbacks `defer()` immediately; `[GamesCog.on_interaction](cogs/games.py)` schedules a fallback
  that replies with `[interactions.pagination_outdated](configuration/locale/en.toml)` (or `pagination_not_yours`)
  when no registered view handled the component. Button `custom_id`s only encode guild/user (no recoverable query state).
- Remove all instances of the first time welcome message. There's no point.
  - **Done:** Removed `check_and_send_first_time_welcome` / `FirstTimeUserEmbed` usage.

## Bugs/Visuals (later)

- The leaderboard looks like crap
- Many matrix-like displays (such as the game queue) don't render well on mobile
- Inconsistent styling between /history and /profile for individual games
- Cross-game slash safety: invoking another game's move (or a missing subcommand) can crash or behave oddly if
command names overlap or the tree doesn't match expectations.

## Website (later)

- playcord.github.io
  - Needs to contain:
    - Homepage with bot features and invite link
    - Bot API docs
    - Guides for games (already linked to at playcord.github.io/learn/)
    - Privacy policy/TOS

