# PlayCord Game Author Guide

PlayCord game authors should only need three surfaces:

1. `playcord/api/__init__.py` for runtime primitives.
2. `playcord/api/__init__.py` for metadata (`GameMetadata`, `Move`, `MoveParameter`).
3. `playcord/games/<your_game>.py` for the game implementation and registration.

## Minimal game structure

```python
from playcord.api import GameMetadata, Move, MoveParameter, ParameterKind
from playcord.api import ReplayableGame, GameContext, MessageLayout, Outcome, UpsertMessage, handler
from playcord.api.plugin import register_game


class MyGame(ReplayableGame):
    metadata = GameMetadata(
        key="mygame",
        name="My Game",
        summary="A short summary",
        description="What the game does.",
        move_group_description="Commands for My Game",
        player_count=2,
        author="@you",
        version="1.0",
        author_link="https://github.com/you",
        source_link="https://github.com/PlayCord/bot",
        time="5min",
        difficulty="Easy",
        moves=(
            Move(
                name="move",
                description="Make a move",
                callback=handler("do_move"),
                options=(
                    MoveParameter(
                        name="slot",
                        description="Board slot",
                        kind=ParameterKind.string,
                        autocomplete=handler("autocomplete_slot"),
                    ),
                ),
            ),
        ),
        peek_callback=handler("peek_status"),
    )

    def current_turn(self):
        ...

    def outcome(self):
        ...

    def render(self, ctx: GameContext):
        return (UpsertMessage(target="thread", key="board", layout=MessageLayout(content="...")),)

    def do_move(self, actor, arguments, *, source, ctx):
        ...

    def initial_replay_state(self, ctx: GameContext):
        ...

    def apply_replay_event(self, state, event):
        ...

    def render_replay(self, state):
        ...


game = register_game(MyGame)
```

## Registration and validation

- Use `register_game(MyGame)` exactly once.
- Registration validates configured handlers (`moves`, `autocomplete`, `bots`, `peek`) when the module loads.
- Handler references should use `handler("method_name")` so invalid names fail at startup, not during a live match.

## Runtime move handlers

Games can implement either move signature:

- Legacy: `def do_move(self, actor, arguments, *, source, ctx) -> tuple[...]`
- Typed: `def do_move(self, request) -> tuple[...]` where `request` is `MoveRequest`.

Both are supported by `GameManager`.

## Replay capability

Replay is explicit: games that support replay should inherit `ReplayableGame` and implement:

- `initial_replay_state`
- `apply_replay_event`
- `render_replay`

If a game does not implement replay, the replay viewer will fall back to textual event output.
