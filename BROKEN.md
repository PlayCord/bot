# BROKEN.md

The idea of this file is to store everything known to be broken, as well as the new features I want to add. When this is
empty, I will release 1.0.0

## Features (focus on this)

- [ ] No match replay functionality (viewer / sharing)
    - **Done (persistence):** On each successful move, `GameInterface` calls `Database.record_move` and
      `append_replay_event` (JSONL on `matches.replay_log`). `Command.is_game_affecting` (default true; Poker/Blackjack
      `peek` = false). Bot moves recorded with bot `user_id`. `Game.attach_replay_logger` / `Game.log_replay_event`
      exist
      for stochastic events—games must call `log_replay_event` where RNG matters (shuffle, dice); not all games do yet.
    - **Still TODO:** Replay viewer UI (embed/pagination or web), shareable replay ID in history, ensuring every
      randomizing game logs stochastic outcomes, broader testing.
    - Replay ID would be displayed in match history.
- [ ] We need a way to prevent people from sending messages in game thread that are not commands, or people spectating
  from sending anything at all. The issue is that the app command and send message privileges are combined.
    - **Partial:** `THREAD_POLICY_PARTICIPANTS_COMMANDS_ONLY` in `configuration/constants.py` (default off) deletes
      non-`/` messages from **participants** in active game threads. Spectators are still non-participants (existing
      warn/delete policy applies); true “spectators silent” may need permission tweaks or stricter deletion.
- [x] Better match history summaries (foundation)
    - **Done:** `Game.match_summary(outcome) -> str | None` on [`api/Game.py`](api/Game.py); stored in
      `matches.metadata.outcome_summary`; shown on game-over embed and in `/playcord history`. Example:
      [`games/TicTacToe.py`](games/TicTacToe.py).
    - **Still TODO:** Implement `match_summary` for other games (chess, poker, etc.) with rich text like “checkmate in
      N.”
- [ ] Better seating algorithm for games. Some games are assymetric (like Mastermind) and seating can have a big impact
  on the game, so we should take that into account when seating players.
    - We would need maybe a way to configure roles for players in each game, and then the seating algorithm would try to
      seat players in a way that balances those roles as much as possible. This would be a pretty complex feature but
      could add a lot of value for certain games. Sometimes it would benefit for this to be random (Secret Hitler), but
      other times we want it to be set. This is something that would be added to the API.
- [ ] Add a feedback command
- [ ] Add customization options for games (board size, wordlist, basically configurable things). This would probably be
  within the matchmaker GUI and not a command (because we don't want to have a /play command for EVERY game
    - There are other questions raised by this:
    - How do we store this information?
    - How do we display it in the matchmaker?
    - How do we handle leaderboards? is there a specified "correct ruleset", or can there be multiple presets? There
      might be several different ways to play a game, and we want that to all be contained within the single game
      instance.
    - This also opens up the possibility of players creating their own custom games by defining the ruleset in a config
      file or something, and then the bot just implements the mechanics of running the game and enforcing the ruleset.
      This is a much more complex feature but could be really cool. Would also force unrated oboviously.
- [x] Rematch button after games
    - **Done:** `RematchView` on the overview message; [`GamesCog.rematch_button_callback`](cogs/games.py) rebuilds a
      lobby with human participants via [`MatchmakingInterface.seed_rematch_players`](utils/interfaces.py).
- [ ] Remove the made with love footer in most locations, except for about command etc
    - `[brand] footer` in locale may still be unused; `/about` uses copyright footer. Sweep game `Footer` components if
      any duplicate the brand line.
- [ ] New custom emojis made for the bot
    - Pixel art, use the blue pixel art duotone
- [ ] Substitution emoji logic is really janky and should be redone, especially for custom emojis
    - **Partial:** [`get_emoji_string`](utils/emojis.py) now coerces emoji ids to int safely; deeper refactor (e.g.
      unified `parse_discord_emoji` path) still optional.
- [ ] Add a better way to limit the bot's scope (full product vision)
    - **Partial today:** Guild setting `playcord_channel_id` in `guilds.settings`; `/playcord set_channel` (admin);
      onboarding mentions it; [`playcord.require_playcord_channel`](configuration/config.yaml) forces `/play` to run
      only
      in that channel when true.
    - **Not done:** Matchmaker UI always posted into the bot channel while `/play` can start elsewhere; thread naming
      `(PlayCord)` cleanup; “everything requires channel if unset” beyond `/play` guard.
- [x] Database problems (Phase 1 foundation — see below; broader schema for leaderboards / presets / replay UI still
  evolves with other features)
    - [x] FFA vs win/loss/tie: `match_participants` uses `final_ranking`; SQL helper
      `calculate_win_loss_tie_from_ranking` exists. **Denormalized `wins` / `losses` / `draws` were removed** from
      `user_game_ratings`; derive outcomes from `match_participants` (see `v_active_leaderboard` / `v_player_stats`).
    - [x] Prevent negative ratings: `mu >= 0` (CHECK + trigger using `games.rating_config.min_mu` + config
      `ratings.min_mu`), plus Python clamps on rating updates.
    - [x] Prevent sigma too small: `sigma >= 0.001` (CHECK + `min_sigma` in rating_config + config `ratings.min_sigma`),
      skill decay and global rating aggregation clamp to the floor.
    - [ ] Broader schema work still tied to leaderboards, customization, full replay pipeline, etc. (ongoing)
    - [x] `matches_played` drift: `sync_games_played_counts()` recomputes from completed matches; runs on bot startup
      (best-effort if the function is missing on ancient DBs).
    - [x] Game registration from code: `sync_games_from_code()` on startup upserts all `GAME_TYPES` entries;
      `games.game_schema_version` and `Game.game_schema_version` for tracking definition changes. **Not yet:** using DB
      state to auto-detect Discord command tree drift (see separate item below).
- [ ] Detect if the synced commands are not equal to the local command tree and auto sync
    - **Partial:** [`bot.auto_sync_commands`](configuration/config.yaml) runs a full `tree.sync()` on startup when true;
      no hash/compare of Discord vs local tree yet.
- [ ] Move the trueskill rating stuff INTO the game class (full modular swap)
    - **Partial:** [`Game.trueskill_scale`](api/Game.py) optional dict (`sigma`/`beta`/`tau`/`draw` as fractions of MU);
      [`game_over`](utils/interfaces.py) uses `trueskill_scale` with `GAME_TRUESKILL` fallback. Per-game DB
      `rating_config` still used for floors/sync elsewhere.
    - **Still TODO:** Single named API like `game.trueskill_parameters`, reading defaults from DB row in one place, drop
      duplication with `GAME_TRUESKILL` when every game defines scales.
- [ ] Error handling (broader coverage)
    - **Partial:** [`successful_matchmaking`](utils/interfaces.py) wrapped; failures edit the lobby message with an
      error embed + traceback (internal path). Other setup paths may still fail quietly.
    - If a crash occurs during game setup or something where it is *our* fault (not within a game's code), we still need
      to show an error consistently everywhere.
- [ ] Analytics viewer of some kind
    - **Partial:** `/playcord analytics` (bot owners) — event counts by type from DB for a look-back window. No charts
      UI
      yet.
    - Migrate this to a message command (playcord/analytics) instead
- [ ] More modular game format
    - Currently all of the games have some kind of "game_message" that is entirely controlled by it (within parameters)
    - It might be good/cool to have a more open format where more messages are sent by the bot in the channel as the
      game progresses, maybe with occassional resets ETC.
    - This would also change the bot-provided current turn embed to a ephmeral notification sent by the bot (or a
      message)
    - This would greatly increase the number of possibilities for games.
    - If this was implemented, it would completely replace the current game infastructure but have such a large
      featureset that implementing a game in the current method would also be trivial
- [x] Pagination after bot restarts (UX)
    - **Done:** Pagination callbacks `defer()` immediately; [`GamesCog.on_interaction`](cogs/games.py) schedules a fallback
      that replies with [`interactions.pagination_outdated`](configuration/locale/en.toml) (or `pagination_not_yours`)
      when no registered view handled the component. Button `custom_id`s only encode guild/user (no recoverable query state).
- [x] Remove all instances of the first time welcome message. There's no point.
    - **Done:** Removed `check_and_send_first_time_welcome` / `FirstTimeUserEmbed` usage.
      namespace.

## Bugs/Visuals (later)

- [ ] The leaderboard looks like crap
- [ ] Many matrix-like displays (such as the game queue) don't render well on mobile
- [ ] Inconsistent styling between /history and /profile for individual games
- [ ] Move commands from other games cause a crash if they don't exist and unintended behavior if they share a

## Website (later)

- [ ] playcord.github.io
    - Needs to contain:
        - [ ] Homepage with bot features and invite link
        - [ ] Bot API docs
        - [ ] Guides for games (already linked to at playcord.github.io/learn/<game>)
        - [x] Privacy policy/TOS
