"""Discord-facing game primitives (commands, components, responses, base game class)."""

from playcord.discord_games.arguments import Argument, Integer, String
from playcord.discord_games.bot import Bot
from playcord.discord_games.command import Command
from playcord.discord_games.exceptions import ContainerValidationError
from playcord.discord_games.game import (
    Game,
    PlayerOrder,
    RoleMode,
    resolve_player_count,
)
from playcord.discord_games.match_options import MatchOptionSpec
from playcord.discord_games.player import Player
from playcord.discord_games.response import Response, ResponseType

__all__ = [
    "Argument",
    "Bot",
    "Command",
    "ContainerValidationError",
    "Game",
    "Integer",
    "MatchOptionSpec",
    "Player",
    "PlayerOrder",
    "Response",
    "ResponseType",
    "RoleMode",
    "String",
    "resolve_player_count",
]
