# PlayCord Plugin API

The refactored PlayCord runtime is organized around a typed core plus an explicit plugin registry. New games are
registered under `playcord/games/` and expose metadata that the command tree, lobby UI, rating system, and replay
pipeline can all consume without special-case code.

## Architecture

PlayCord is now split into four layers:

- `playcord/domain/`: pure game, rating, replay, and player abstractions
- `playcord/infrastructure/`: config, locale, logging, DB pools, migrations, repositories
- `playcord/application/`: session, replay, matchmaking, stats, and analytics services
- `playcord/presentation/`: Discord commands, interaction routing, error handling, and UI views

Game plugins live under `playcord/games/<name>/` and are loaded explicitly from `playcord/games/__init__.py`.

## Plugin Contract

Every game package exposes a `plugin` object implementing the `GamePlugin` protocol from `playcord/games/plugin.py`.

Current built-in games still use `LegacyGamePlugin` adapters:

```python
from playcord.games.plugin import LegacyGamePlugin

plugin = LegacyGamePlugin("tictactoe", "games.TicTacToe", "TicTacToeGame")
```

The long-term native shape is:

```python
from playcord.domain import Game, GameMetadata, Move, MoveParameter, ParameterKind


class MyGame(Game):
    metadata = GameMetadata(
        key="mygame",
        name="My Game",
        summary="A short one-line summary",
        description="Longer explanation of how the game works.",
        move_group_description="Commands for My Game",
        player_count=2,
        author="@you",
        version="1.0",
        author_link="https://github.com/you",
        source_link="https://github.com/you/mygame",
        time="5min",
        difficulty="Easy",
        moves=(
            Move(
                name="move",
                description="Make a move",
                options=(
                    MoveParameter(
                        name="column",
                        description="Column number",
                        kind=ParameterKind.integer,
                        min_value=1,
                        max_value=7,
                    ),
                ),
                callback="move",
            ),
        ),
    )

    def current_turn(self):
        ...

    def outcome(self):
        ...
```

## Canonical Domain Types

Use `playcord/domain/` as the source of truth:

- `Player`: canonical player model for Discord users, bots, and ratings
- `Rating`: TrueSkill wrapper with conservative/display helpers
- `Move` and `MoveParameter`: typed command metadata
- `MatchOptionSpec`: lobby customization definition
- `GameMetadata`: plugin-facing metadata consumed by commands and UI
- `DomainError` hierarchy: `ValidationError`, `RuleViolation`, `IllegalMove`, `NotPlayersTurn`

Discord-facing game primitives (base `Game` class, `Message`/`Container` trees, `Command`/`Response`, etc.) live in
`playcord/discord_games/`. Domain types (`playcord/domain/`) stay separate from Discord presentation.

## Command Registration

Slash commands are built programmatically in `playcord/presentation/commands/tree.py`. The runtime no longer relies on
generated source strings or `exec()` to define move commands.

The command tree reads plugin metadata and creates:

- one top-level `/play` command
- one slash group per registered game
- one move command per `Move`
- autocomplete handlers from `MoveParameter.autocomplete`

## UI Model

Shared UI primitives live under `playcord/presentation/ui/`:

- `View`
- `Container`
- `Section`
- `TextDisplay`
- `Button`
- `Select`
- `Media`

High-level views such as `ErrorView`, `UserErrorView`, `LobbyView`, and `BoardView` wrap those primitives so commands
and interaction handlers can share one styling surface.

## Error Handling

App command failures route through `playcord/presentation/interactions/errors.py`, which maps exception types to
localized user-visible responses. Domain and application code should raise typed exceptions instead of raw `ValueError`
or bare strings.

## Repository Pattern

Database access is owned by `playcord/infrastructure/db/`:

- `PoolManager`: connection lifecycle
- `MigrationRunner`: schema/application startup tasks
- `PlayerRepository`, `GameRepository`, `MatchRepository`, `ReplayRepository`, `AnalyticsRepository`

Application services consume repositories through `ApplicationContainer`.

## Migration Notes

Current built-in games (`tictactoe`, `connectfour`, `nim`) still use `LegacyGamePlugin` adapters while the older game
implementations are being folded into the new package structure. New games should be authored directly against the
`playcord/domain/` and `playcord/presentation/ui/` APIs.
