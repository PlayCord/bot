<div align="center">

  <h1>
    <img src="docs/playcord_logo.jpg" alt="PlayCord icon" width="80" align="center" /> PlayCord
  </h1>

  <p><em>A Discord bot for turn-based & paper/pencil games, written in Python</em></p>
  <p>
    <a href="#"><img src="https://img.shields.io/badge/python-3.12-blue?logo=python" alt="python" /></a>
    <a href="#"><img src="https://img.shields.io/badge/license-GPLv3-green?logo=opensourceinitiative" alt="license" /></a>
    <a href="https://github.com/playcord/bot"><img src="https://img.shields.io/github/stars/quantumbagel/playcord?style=social" alt="GitHub stars" /></a>
  </p>

</div>

## About

PlayCord aims to provide an easy-to-use framework and bot that can host classic paper-and-pencil games on Discord. The
bot supports multiple games, matchmaking, and TrueSkill-based rankings, all accessible through intuitive slash commands
and button interactions.
> If you think this is cool, please (1) star the project and (2) follow me, it helps motivate me to keep improving the
> project :D

## Features

- TrueSkill-based rankings (the same ELO used by Rocket League and Halo) with global and server leaderboards
- Create new games with a simple Python API
- Persistent leaderboards, match history, and analytics
- Can use buttons, selects, or slash commands for moves, depending on the game

## Bot Usage

### Starting a Game

```
/play <game>              Start a new game
/play tictactoe           Start Tic-Tac-Toe
/play connectfour rated:false   Start an unrated game
/play nim private:true   Start a private game
```

### During Games

- Click buttons to make moves (game-specific)
- Use `/move` commands for complex actions
- Games run in threads for clean organization

### Profile & Stats

```
/playcord profile [@user]   View player profile and ratings
/playcord history <game>    View match history and rating trend
/playcord leaderboard <game>         View server or global rankings
/playcord catalog           Browse available games
```

### Settings

```
/playcord settings          Configure game/bot preferences
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Discord bot token

> **Note:** Docker Compose is the easiest supported setup method. The repo also supports local Python development via
> `pip install -e .[dev]`.

### Installation

1. **Clone the repository:**

```bash
git clone https://github.com/playcord/bot.git
cd playcord
```

2. **Configure the bot:**

```bash
cp playcord/configuration/config.yaml.example playcord/configuration/config.yaml
# Edit config.yaml with your Discord bot token
```

Open `playcord/configuration/config.yaml` and add your Discord bot token and any other settings you want to customize.

3. **Start everything with Docker Compose:**

```bash
docker compose up -d
```

This will start both the PostgreSQL database and the bot in containers. The database will be automatically initialized
with the schema on first run, and the bot entrypoint will run through `playcord.presentation.bot`.

That's it! Your bot is now running. Use `docker compose logs -f bot` to view the bot logs.

## API Usage

PlayCord provides a runtime game API for creating new games. See [docs/API.md](docs/API.md) for the current contract.
For database and repository contributions, use [docs/PERSISTENCE_GUIDE.md](docs/PERSISTENCE_GUIDE.md).

### Quick Example

```python
from playcord.api import GameMetadata, Move, MoveParameter, ParameterKind
from playcord.api import MessageLayout, ReplayableGame, UpsertMessage, handler
from playcord.api.plugin import register_game


class MyGame(ReplayableGame):
    metadata = GameMetadata(
        key="mygame",
        name="My Game",
        summary="Example game",
        description="Example game description",
        move_group_description="Commands for My Game",
        player_count=2,
        author="@you",
        version="1.0",
        author_link="https://github.com/you",
        source_link="https://github.com/PlayCord/bot",
        time="2min",
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
                    ),
                ),
            ),
        ),
    )

    def render(self, ctx):
        return (
            UpsertMessage(
                target="thread",
                key="board",
                layout=MessageLayout(content=f"Turn: {self.current_turn().mention}"),
            ),
        )

    def current_turn(self):
        ...

    def do_move(self, actor, arguments, *, source, ctx):
        ...

    def initial_replay_state(self, ctx):
        ...

    def apply_replay_event(self, state, event):
        ...

    def render_replay(self, state):
        ...

    def outcome(self):
        return None


game = register_game(MyGame)
```

## Status

See [BROKEN.md](BROKEN.md) for the remaining product backlog and follow-up work.

## License

GPLv3 License - see LICENSE for details.
