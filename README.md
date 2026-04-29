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

> [!IMPORTANT]
> If you think this is cool, please (1) star the project and (2) follow me, it helps motivate me to keep improving the
> project :D

## Features

> [!NOTE]
> This is a non-exhaustive list of features that are currently implemented or planned for the near future.
> See [BROKEN.md](BROKEN.md) for a more detailed list of remaining work.

- TrueSkill-based rankings (the same ELO used by Rocket League and Halo) with global and server leaderboards
- Create new games with a simple Python API
- Persistent leaderboards, match history, and analytics
- Can use buttons, selects, or slash commands for moves, depending on the game
- Replays that reconstruct game state from move events, with interactive UI controls to step through the replay

## License

GPLv3 License - see LICENSE for details.
