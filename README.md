<!-- Logo (small icon to the left of main logo) -->
<!-- Header: icon and title on one line -->
<div style="text-align:center;">
  <img src="docs/playcord_logo.jpg" alt="PlayCord icon" width="80" style="vertical-align:middle; margin-right:12px; height:auto;" />
  <h1 style="display:inline; vertical-align:middle; margin:0; font-size:48px;">PlayCord</h1>
  <div style="margin-top:6px;">
    <em>A Discord bot for turn-based & paper/pencil games</em>
  </div>
  <div>by <a href="https://github.com/quantumbagel">@quantumbagel</a></div>
</div>

<!-- Badges (centered) -->
<div style="text-align:center; margin:8px 0 16px 0;">
  <a href="#"><img src="https://img.shields.io/badge/python-3.12-blue?logo=python" alt="python" style="vertical-align:middle; margin-right:8px;"/></a>
  <a href="#"><img src="https://img.shields.io/badge/license-MIT-green?logo=opensourceinitiative" alt="license" style="vertical-align:middle; margin-right:8px;"/></a>
  <a href="https://github.com/quantumbagel/playcord"><img src="https://img.shields.io/github/stars/quantumbagel/playcord?style=social" alt="GitHub stars" style="vertical-align:middle;"/></a>
</div>

## About

PlayCord aims to provide an easy-to-use framework and bot that can host classic paper-and-pencil games on Discord. The
project focuses on an extensible game API, server-side match state management, SVG rendering for game boards, and a
PostgreSQL-backed leaderboard with TrueSkill-style ratings.

### TLDR: Games, on Discord, without Activities.

> If you think this is cool, please (1) star the project and (2) follow me, it helps motivate me to keep improving the
> project :D

## Features

- **🎮 Multiple Games** - Tic-Tac-Toe, Connect Four, Reversi, Battleship, Liar's Dice, and more
- **📊 Rating System** - TrueSkill-based rankings with global and server leaderboards
- **🔧 Extensible API** - Create new games with a simple Python API
- **🗄️ PostgreSQL Backend** - Persistent leaderboards, match history, and analytics
- **🌐 Cross-Server Play** - Match with players across different Discord servers
- **🎨 Rich UI** - Button-based gameplay with emoji support

## Games

### Implemented ✅
| Game | Players | Description |
|------|---------|-------------|
| Tic-Tac-Toe | 2 | Classic Xs and Os |
| Connect Four | 2 | Drop discs to connect four |
| Reversi | 2 | Flip opponent's pieces |
| Battleship | 2 | Sink the enemy fleet |
| Liar's Dice | 2-6 | Bluffing dice game |
| Nim | 2-4 | Take stones strategically |
| Mastermind Duel | 2 | Code-breaking game |
| No Thanks! | 3-7 | Card avoidance game |
| Blackjack Table | 2-7 | Multiplayer blackjack |
| Codenames Lite | 4-8 | Word association team game |

### Planned 🚧
| Game | Status |
|------|--------|
| Poker (Texas Hold'em) | In Development |
| Chess | In Development |

## Bot Usage

### Starting a Game
```
/play <game>              Start a new game
/play tictactoe           Start Tic-Tac-Toe
/play connectfour rated:false   Start an unrated game
```

### During Games
- Click buttons to make moves (game-specific)
- Use `/move` commands for complex actions
- Games run in private threads for clean organization

### Profile & Stats
```
/playcord profile [@user]   View player profile and ratings
/playcord history <game>    View match history and rating trend
/leaderboard <game>         View server or global rankings
/playcord catalog           Browse available games
```

### Settings
```
/playcord settings          Configure game preferences
```

## Quick Start

### Prerequisites
- Python 3.12+
- PostgreSQL database
- Discord bot token

### Installation

1. **Clone the repository:**
```bash
git clone https://github.com/quantumbagel/playcord.git
cd playcord
```

2. **Install dependencies:**
```bash
pip install -e .
# or with poetry
poetry install
```

3. **Start the database:**
```bash
docker-compose up -d
```

4. **Configure the bot:**
```bash
cp configuration/config.yaml.example configuration/config.yaml
# Edit config.yaml with your Discord token and database credentials
```

5. **Run the bot:**
```bash
python bot.py
```

## API Usage

PlayCord provides a simple API for creating new games. See [docs/API.md](docs/API.md) for full documentation.

### Quick Example
```python
from api.Game import Game
from api.Command import Command
from api.MessageComponents import Description, Button

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

## Documentation

- [API Documentation](docs/API.md) - Game development API
- [Database Schema](DATABASE_SETUP.md) - PostgreSQL schema reference
- [Code Review](CODE_REVIEW.md) - Architecture notes

## Project Structure

```
playcord/
├── api/                 # Game API interfaces
│   ├── Game.py         # Base game class
│   ├── Player.py       # Player representation
│   ├── Command.py      # Move/action definitions
│   └── MessageComponents.py  # UI components
├── games/              # Game implementations
├── cogs/               # Discord bot commands
├── utils/              # Utilities (database, views, etc.)
├── configuration/      # Config files
├── docs/               # Documentation
└── tests/              # Test suite
```

## Current Status

### Completed ✅
- PostgreSQL database with comprehensive schema
- Emoji API (`register_emoji()`, `get_emoji()`)
- Leaderboards with pagination
- Profile and stats commands
- Analytics event system
- Cross-server matchmaking infrastructure
- Game settings configuration
- Permission hardening for game interactions
- Thread message policy for non-participants
- Button emoji support

### In Progress 🚧
- Poker (Texas Hold'em)
- Chess

## Contributing

Contributions are welcome! Please check the issues for tasks or open a new one.

## License

MIT License - see LICENSE for details.

---

If you find this project cool, please ⭐ star the repository!
