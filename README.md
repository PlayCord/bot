<div align="center">

  <h1>
    <img src="docs/playcord_logo.jpg" alt="PlayCord icon" width="80" align="center" /> PlayCord
  </h1>

  <p><em>A Discord bot for turn-based & paper/pencil games, written in Python</em></p>
  <p>
    <a href="#"><img src="https://img.shields.io/badge/python-3.12-blue?logo=python" alt="python" /></a>
    <a href="#"><img src="https://img.shields.io/badge/license-GPLv3-green?logo=opensourceinitiative" alt="license" /></a>
    <a href="https://github.com/quantumbagel/playcord"><img src="https://img.shields.io/github/stars/quantumbagel/playcord?style=social" alt="GitHub stars" /></a>
  </p>

</div>

## About

PlayCord aims to provide an easy-to-use framework and bot that can host classic paper-and-pencil games on Discord. The
project now uses a layered `playcord/` package for domain logic, repositories, services, commands, and UI, while
legacy modules remain only as compatibility shims during the migration.

### TLDR: Games, on Discord, without needing Activities.

> If you think this is cool, please (1) star the project and (2) follow me, it helps motivate me to keep improving the
> project :D

## Features

- Many games supported: Tic-Tac-Toe, Connect Four, Reversi, Battleship, Liar's Dice, and more
- TrueSkill-based rankings (the same ELO used by Rocket League and Halo) with global and server leaderboards
- Create new games with a simple Python API
- Persistent leaderboards, match history, and analytics
- Match with players across different Discord servers
- Button-based gameplay with emoji support

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
- Games run in private threads for clean organization

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
git clone https://github.com/quantumbagel/playcord.git
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

PlayCord provides a plugin API for creating new games. See [docs/API.md](docs/API.md) for the current plugin contract.

### Quick Example

```python
from playcord.discord_games.command import Command
from playcord.discord_games.game import Game
from playcord.discord_games.message_components import Message, TextDisplay


class MyGame(Game):
    name = "My Game"
    player_count = 2
    moves = [Command(name="move", description="Make a move", callback="do_move")]

    def __init__(self, players):
        self.players = players
        self.turn = 0

    def state(self):
        return Message(TextDisplay(f"Turn: {self.current_turn().mention}"))

    def current_turn(self):
        return self.players[self.turn]

    def do_move(self, player):
        self.turn = (self.turn + 1) % len(self.players)

    def outcome(self):
        return None  # Game ongoing
```

## Dependencies

### Core

- `discord.py` - Discord API wrapper
- `psycopg` / `psycopg_pool` - PostgreSQL driver
- `trueskill` - Rating system
- `ruamel.yaml` - Configuration parsing

### Optional

- `cairosvg` - SVG rendering for game boards
- `pillow` - Image manipulation

PlayCord now uses SVG-based board renders (converted to PNG for Discord attachments) for visual-heavy games like Chess,
Connect Four, and Battleship peek views when `cairosvg` is available.

## Project Structure

Runtime code and bundled assets live under the `playcord` Python package:

```
playcord/
├── domain/              # Pure game/rating/player abstractions
├── infrastructure/      # Config, locale, logging, DB pool/repos, SQL assets
├── application/       # Matchmaking/session/replay/stats services
├── presentation/      # Bot entry, commands, cogs, UI, interaction router
├── games/             # Plugin registry (metadata + legacy game loader)
├── games_impl/        # Bundled Discord game classes (Tic-tac-toe, Nim, Connect Four)
├── discord_games/     # Shared Discord primitives (Game ABC, components, Response)
├── utils/             # Database layer, Discord helpers, analytics, locale shim
├── configuration/   # config.yaml, emoji.yaml, locale TOML
└── cli/               # `playcord-cli` entrypoints

docs/                    # Documentation (outside the installable package)
tests/                   # Test suite
```

## Status

See [BROKEN.md](BROKEN.md) for the remaining product backlog and follow-up work.

## License

GPLv3 License - see LICENSE for details.
