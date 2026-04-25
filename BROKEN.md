# features to add

## 0.8.0

- Replay UX update
    - Recent games needs to show the outcome
    - Outcome is a string, one for the game (e.g. Liberals won by passing 5 liberal policies), and one for each player (
      e.g. Facist team, lost because 5 liberals passed)
    - Fix this atrocity: `Tic-Tac-Toe · 1st/1 | seat #1 | rated | completed | 0`
        - It's impossible to tell what is going on. The seat doesn't matter? The placement doesn't matter? This should
          look something like this
        - `Tic-Tac-Toe (f87ab68) · Draw | rated | +0`
        - where the f87... is the replay ID, "Draw" is the game outcome, and +0 is the rating change for the player.
    - Turn-by-turn replay viewer
        - Problem: replays are currently a raw list of events which is hard to read for board/turn-based games.
          We should provide an interactive, turn-by-turn viewer that replays the game state visually.
        - Requirements / notes:
            - Provide a per-game renderer that can apply replay events to reconstruct state (or store snapshots)
              and render a UI message showing the current state (board, player turn, summary).
            - UI controls: previous/next move buttons, jump-to-start/end, and optionally a move list/seek bar.
            - Use existing channel components (buttons/selects) and make sure messages are editable safely with
              components v2 content rules.
            - Persist minimal metadata in the replay (initial state or snapshots every N moves) to avoid
              replay-time heavy computation for very long games.
            - Add a helper API for games to produce a visual representation and to apply a single replay event.
            - Tests: verify reconstruction from events and UI navigation (edge cases: interrupted games, forfeits).
- Standardize ELO
    - The leaderboard uses CR (mu - 3 * sigma) but everything else uses mu. Standarize all display values to show CR (as
      ELO). Also, update the trueskill constants for the starting rating, and remove mu from display. This is because we
      want to
      calculate the starting mu as starting rating + 3 * starting sigma, so that new players start with the same
      displayed rating as before.
- API updates
    - Delete LegacyGamePlugin
    - Remove GamePlugin class attributes and simply make it the metadata (GameMetadata) object
    - Fix metadata not being used
        - metadata fields carry callback names (e.g. `Move.callback`,
          `MoveParameter.autocomplete`, `BotDefinition.callback`) but the runtime calls
          instance methods on `GamePlugin` (`apply_move`, `autocomplete`, `bot_move`, `peek`).
          As a result the string callbacks in metadata are ignored. The runtime should
          be changed so metadata callbacks are resolved and used (metadata is the
          canonical source for move/autocomplete/bot callbacks). The other functions (`apply_move`, `autocomplete`,
          `bot_move`, `peek`) can be removed from `GamePlugin` since they are redundant with the metadata callbacks.

# 0.9.0

- Command / settings rework
    - Move `/playcord set_channel` into the new `/playcord settings` (the channel config becomes a bot-level setting).
    - Rename the current `/playcord settings` command to `/playcord configure` so it continues to expose server/game
      configuration.
    - `/playcord settings` will become the place for bot-level settings (e.g. where the bot posts replays, default
      behaviors, and global preferences).
    - Permissions: all `/playcord settings` subcommands must require "Manage Server" or higher.
    - Brainstormed bot-level settings to include in `/playcord settings`:
        - `channel` (channel for announcements, replays, and default game posts)
        - `locale` (default locale for messages) default is english
        - `play_role` (role required to create/join games)
        - `admin_roles` (roles that get elevated bot admin privileges)
        - `audit_channel` (channel where configuration changes are posted, if any). Default is off
    - Rationale: separating bot-level settings from server/game configuration makes permissions clearer and groups
      cross-cutting preferences in a single place.

- Remove `/playcord invite`
    - Remove the legacy `/playcord invite` command.

- New `/playcord bot` lobby command
    - Purpose: replace bot-related `/playcord invite` params with explicit bot controls for the current matchmaking
      lobby.
    - Current model to align with:
        - bots are game-defined difficulties from `GameMetadata.bots` (`BotDefinition`), not server-managed bot
          accounts.
        - when added, a bot is a synthetic `Player` (`is_bot=True`, `bot_difficulty=<difficulty>`), and moves come
          from the game's bot callback.
        - no guild-level bot registry, role assignment, avatar management, or per-server bot profiles today.
    - Permissions / scope:
        - same as other lobby mutations: only the lobby creator can add/remove bots.
        - listing can be available to anyone in the lobby.
    - Subcommands and behaviors:
        - `add <difficulty>` — add one bot with a supported difficulty for the active lobby game.
        - `remove <name>` — remove a queued bot from the active lobby.
        - `list` — show available difficulties for the game and bots currently queued in the lobby.
    - Validation rules to keep consistent with existing behavior:
        - command only works when the caller is in an active lobby.
        - fail if the selected game does not expose bot difficulties.
        - enforce player-count limits when adding bots.
        - keep one bot per difficulty unless we explicitly decide to allow duplicates.
        - adding any bot forces the lobby to unrated.
    - Rationale: this matches how bots already work (lobby participants generated from game-provided difficulties) and
      avoids introducing a server-level bot system that does not exist in the current architecture.

- Plugin-owned role system (players + bots)
    - Goal: role assignment is owned entirely by game plugins through API functions; runtime/lobby framework should not
      contain role-assignment logic.
    - Capability rule:
        - if a plugin does not implement the role API, that game does not support roles.
        - if implemented, plugin defines the supported role behavior via metadata.
    - Metadata-defined role flows:
      -
            1) Selectable roles only:

            - plugin exposes a metadata option with role IDs and human-readable role names.
            - lobby shows role selectors (for example, per-player dropdowns) and displays selected roles next to player
              names in matchmaking.
            - after each role update, call `validate_roles(...)`; it returns whether the lobby is startable and may
              include an optional error message.
        -
            2) Random roles only:

            - no role selection UI and no role visibility in matchmaking.
            - `assign_roles(...)` returns a valid player-to-role mapping for match start and does not mutate lobby
              player state directly.
        -
            3) Selectable + random:

            - selectable-role UI is shown, and selected roles are visible in matchmaking.
            - add an `Assign Roles` button to the left of `Ready` to run plugin assignment for the lobby.
        -
            4) No role support:

            - no role UI, no role display in matchmaking, and no role operations for that game.
    - Plugin role API contract (high level):
        - `validate_roles(...)` - checks whether current lobby role state is valid and may provide an error message.
        - `role_selection_options(...)` - returns per-player role choices for lobby UI, if any.
        - `assign_roles(...)` - returns final player order and role assignment for match start.
    - Runtime/lobby responsibilities (pass-through only):
        - detect role metadata/API support and only show role UI when supported by the selected flow.
        - call plugin APIs and propagate plugin validation errors to users.
        - persist plugin-resolved role assignment/seat order for replay and rematch determinism.
        - expose plugin-resolved roles in match context for rendering and bot decisions.
    - Bot roles and AI:
        - bots get roles only through the same plugin role API path.
        - role-specific bot behavior is plugin-defined; no generic runtime role strategy.
    - Validation and tests:
        - add tests that assert unsupported plugins have no role UX and reject role operations cleanly.
        - add tests for plugins that do implement role APIs (humans + bots, edge cases, replay consistency).

- API documentation / pdoc configuration
    - Add docstrings to all public API functions and classes, and configure pdoc to generate documentation from these
      docstrings.
    - Ensure that the generated documentation is comprehensive and easy to navigate for developers.
    - Update the playcord.github.io site to include the new documentation and make it the primary reference for
      developers using the PlayCord API.
