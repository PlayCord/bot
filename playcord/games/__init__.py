"""Canonical game registry exports."""

from playcord.api.plugin import get_registered_game, iter_registered_games
from playcord.games import (
    mafia as _mafia,
    secret_hitler as _secret_hitler,
    tictactoe as _tictactoe,
)

GAMES = list(iter_registered_games())
GAME_BY_KEY = {game.key: game for game in GAMES}

__all__ = [
    "GAMES",
    "GAME_BY_KEY",
    "_mafia",
    "_secret_hitler",
    "_tictactoe",
    "get_registered_game",
    "iter_registered_games",
]
