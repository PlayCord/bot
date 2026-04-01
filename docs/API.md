# PlayCord API Documentation

This document describes the core API for creating games in PlayCord.

## Overview

PlayCord uses a component-based architecture where games inherit from the `Game` base class and implement required
methods. The framework handles Discord integration, turn management, and rating updates.

## Quick Start

```python
from api.Game import Game
from api.Command import Command
from api.Arguments import Integer
from api.Player import Player
from api.MessageComponents import Description, Button, ButtonStyle
from api.Response import Response


class MyGame(Game):
    name = "My Game"
    players = 2
    moves = [Command(name="move", description="Make a move", callback="do_move")]

    def __init__(self, players):
        self.players = players
        self.turn = 0

    def state(self):
        return [Description(f"Turn: {self.current_turn().mention}")]

    def current_turn(self):
        return self.players[self.turn]

    def do_move(self, player):
        self.turn = (self.turn + 1) % len(self.players)
        return None  # Silent success

    def outcome(self):
        return None  # Game ongoing
```

---

## Core Classes

### Game (api/Game.py)

The base class for all games. Inherit from this and implement required methods.

#### Class Attributes

| Attribute                        | Type               | Description                                    |
|----------------------------------|--------------------|------------------------------------------------|
| `name`                           | `str`              | Human-readable game name                       |
| `players`                        | `int \| list[int]` | Allowed player counts (e.g., `2` or `[2,3,4]`) |
| `description`                    | `str`              | Full game description                          |
| `summary`                        | `str`              | Short description for `/play` command          |
| `move_command_group_description` | `str`              | Description for move commands                  |
| `moves`                          | `list[Command]`    | Available player commands                      |
| `bots`                           | `dict[str, Bot]`   | Optional bot difficulties (for AI opponents)   |
| `author`, `version`              | `str`              | Game metadata                                  |
| `time`, `difficulty`             | `str`              | Estimated duration and difficulty              |
| `player_order`                   | `PlayerOrder`      | How to order players (default: `RANDOM`)       |

#### Required Methods

```python
def __init__(self, players: list[Player]) -> None:
    """Initialize game state with the given players."""


def state(self) -> list[MessageComponent]:
    """Return current game state as UI components."""


def current_turn(self) -> Player:
    """Return the player whose turn it is. Should be O(1)."""


def outcome(self) -> Player | list[list[Player]] | None:
    """
    Return game result:
    - Single Player: That player won
    - list[list[Player]]: Ranked groups [[1st], [2nd], ...]
    - None: Game still in progress
    """
```

#### PlayerOrder Enum

```python
from api.Game import PlayerOrder


class MyGame(Game):
    player_order = PlayerOrder.CREATOR_FIRST  # Creator goes first
    # Options: RANDOM, PRESERVE, CREATOR_FIRST, REVERSE
```

---

### Player (api/Player.py)

Represents a player with TrueSkill rating support.

#### Properties

| Property              | Type    | Description                              |
|-----------------------|---------|------------------------------------------|
| `id`                  | `int`   | Discord user ID                          |
| `name`                | `str`   | Display name                             |
| `mu`                  | `float` | TrueSkill skill estimate (default: 1000) |
| `sigma`               | `float` | TrueSkill uncertainty                    |
| `mention`             | `str`   | Discord mention string `<@id>`           |
| `conservative_rating` | `float` | `mu - 3*sigma` (for leaderboards)        |
| `display_rating`      | `int`   | Rounded mu                               |
| `player_data`         | `dict`  | Store arbitrary game-specific data       |

#### Methods

```python
player.get_formatted_elo(uncertainty_threshold=0.20)  # Returns "1000" or "1000?"
```

---

### Command (api/Command.py)

Defines a player action/move.

```python
Command(
    name="drop",  # Slash command name
    description="Drop a disc",  # Help text
    options=[Integer(...)],  # Arguments (optional)
    callback="drop_disc",  # Method name to call
    require_current_turn=True  # Only current player can use
)
```

---

### Bot (api/Bot.py)

Defines one AI difficulty option for a game.

```python
from api.Bot import Bot

class MyGame(Game):
    bots = {
        "easy": Bot(description="Random legal move", callback="bot_easy"),
        "hard": Bot(description="Strong tactical play", callback="bot_hard"),
    }

    def bot_easy(self, bot_player):
        return {"name": "move", "arguments": {"pos": "1,1"}}
```

Bot callbacks can return:

- `{"name": "<move_command>", "arguments": {...}}`
- `("<move_command>", {...})`
- A direct move callback result (`Response` or `None`)

### Arguments (api/Arguments.py)

Argument types for commands.

#### String

```python
String(argument_name="move", description="Board position", autocomplete="ac_move")
```

#### Integer

```python
Integer(argument_name="column", description="Column (1-7)", min_value=1, max_value=7)
```

#### Dropdown

```python
Dropdown(argument_name="choice", description="Pick one",
         options={"Option A": "a", "Option B": "b"})
```

---

### MessageComponents (api/MessageComponents.py)

UI components returned by `state()`.

#### Embed Components

```python
Description("Game status text")  # Embed description
Field("Title", "Value", inline=False)  # Embed field
DataTable({player: {"Score": 10}})  # Auto-formatted player data
Image(png_bytes)  # Attach image
Footer("Footer text")  # Embed footer
```

#### Interactive Components

```python
Button(
    label="Click Me",
    callback=self.on_click,
    emoji="🎮",
    row=0,  # 0-4
    style=ButtonStyle.success,  # blurple/grey/green/red
    arguments={"x": 1, "y": 2},  # Passed to callback
    require_current_turn=True,
    disabled=False
)

Dropdown(
    data=[{"label": "A", "value": "a"}],
    callback=self.on_select,
    placeholder="Choose...",
    min_values=1,
    max_values=1
)
```

---

### Response (api/Response.py)

Return from move callbacks to send messages.

```python
# Error message (only player sees, auto-deletes)
return Response(
    content="Invalid move!",
    ephemeral=True,
    delete_after=5
)

# Silent success (framework updates display)
return None
```

---

## Patterns & Best Practices

### Turn Management

```python
def __init__(self, players):
    self.players = players
    self.turn = 0


def current_turn(self):
    return self.players[self.turn]


def advance_turn(self):
    self.turn = (self.turn + 1) % len(self.players)
```

### Move Validation

```python
def drop(self, player, column):
    if column < 1 or column > 7:
        return Response(content="Invalid column!", ephemeral=True, delete_after=5)

    if self.column_full(column):
        return Response(content="Column is full!", ephemeral=True, delete_after=5)

    # Valid move - apply it
    self.board[column].append(player)
    self.advance_turn()
    return None  # Success
```

### Outcome Formats

```python
# Single winner
def outcome(self):
    if self.winner:
        return self.winner
    return None


# Ranked results (multiplayer)
def outcome(self):
    if self.game_over:
        # [[1st place], [2nd place], [3rd place]]
        return [[self.winner], [self.second], [self.third]]
    return None


# Draw (tie for 1st)
def outcome(self):
    if self.draw:
        return [[player1, player2]]  # Both tied for 1st
    return None
```

### Autocomplete

```python
class MyGame(Game):
    moves = [Command(name="move", options=[
        String(argument_name="pos", autocomplete="ac_positions")
    ])]

    def ac_positions(self, player):
        # Return list of {display: value} dicts
        return [
            {"Top Left": "0,0"},
            {"Center": "1,1"},
        ]
```

---

## File Structure

```
api/
├── Game.py           # Base Game class
├── Player.py         # Player representation
├── Command.py        # Move/action definitions
├── Arguments.py      # Command argument types
├── MessageComponents.py  # UI components
└── Response.py       # Response handling

games/
├── TicTacToe.py      # Example: 2-player, simple
├── ConnectFour.py    # Example: 2-player, board game
├── LiarsDice.py      # Example: 2-6 players
├── NoThanks.py       # Example: 3-7 players, card game
└── ...
```
