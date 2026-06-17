"""Canonical game registry: exports the built-in games available to PlayCord."""

from __future__ import annotations

try:
    from playcord.api.plugin import get_registered_game, iter_registered_games
    from playcord.games import (
        mafia as _mafia,
        secret_hitler as _secret_hitler,
        tictactoe as _tictactoe,
    )

    GAMES = list(iter_registered_games())
    GAME_BY_KEY = {game.key: game for game in GAMES}
except ImportError:
    GAMES = []
    GAME_BY_KEY = {}

    def get_registered_game(key: str):  # noqa: ANN202
        return GAME_BY_KEY.get(key)

    def iter_registered_games():  # noqa: ANN202
        return iter(GAMES)


__all__ = [
    "GAMES",
    "GAME_BY_KEY",
    "get_registered_game",
    "iter_registered_games",
]
