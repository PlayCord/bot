"""
Resolve TrueSkill sigma/beta/tau/draw fractions for a game type key.

Runtime reads come from ``games.rating_config`` in the database. This module keeps a
seed map only for startup/bootstrap before the DB-backed registry is available.
"""

from __future__ import annotations

import importlib

DEFAULT_TRUESKILL_FRACTIONS: dict[str, dict[str, float]] = {
    "tictactoe": {"sigma": 1 / 6, "beta": 1 / 12, "tau": 1 / 100, "draw": 9 / 10},
    "liars": {"sigma": 1 / 2.5, "beta": 1 / 5, "tau": 1 / 250, "draw": 0},
    "test": {"sigma": 1 / 3, "beta": 1 / 5, "tau": 1 / 250, "draw": 0},
    "connectfour": {"sigma": 1 / 6, "beta": 1 / 12, "tau": 1 / 120, "draw": 1 / 10},
    "reversi": {"sigma": 1 / 5, "beta": 1 / 10, "tau": 1 / 150, "draw": 1 / 20},
    "nim": {"sigma": 1 / 4, "beta": 1 / 8, "tau": 1 / 150, "draw": 0},
    "mastermind": {"sigma": 1 / 4, "beta": 1 / 8, "tau": 1 / 180, "draw": 0},
    "battleship": {"sigma": 1 / 4, "beta": 1 / 8, "tau": 1 / 180, "draw": 0},
    "nothanks": {"sigma": 1 / 3, "beta": 1 / 6, "tau": 1 / 200, "draw": 0},
    "blackjack": {"sigma": 1 / 3, "beta": 1 / 6, "tau": 1 / 200, "draw": 1 / 5},
    "poker": {"sigma": 1 / 3, "beta": 1 / 6, "tau": 1 / 200, "draw": 0},
    "chess": {"sigma": 1 / 5, "beta": 1 / 10, "tau": 1 / 150, "draw": 1 / 10},
}


def get_seed_trueskill_fractions(game_type_key: str) -> dict[str, float]:
    """Bootstrap/default fractions before the DB-backed game registry is available."""
    from api.Game import Game
    from configuration.constants import GAME_TYPES

    spec = GAME_TYPES.get(game_type_key)
    if spec:
        mod_name, cls_name = spec
        try:
            mod = importlib.import_module(mod_name)
            cls = getattr(mod, cls_name)
            if isinstance(cls, type) and issubclass(cls, Game):
                base = dict(
                    DEFAULT_TRUESKILL_FRACTIONS.get(
                        game_type_key,
                        DEFAULT_TRUESKILL_FRACTIONS["tictactoe"],
                    )
                )
                over = getattr(cls, "trueskill_scale", None)
                if over:
                    base.update(over)
                return base
        except Exception:
            pass
    return dict(
        DEFAULT_TRUESKILL_FRACTIONS.get(
            game_type_key,
            DEFAULT_TRUESKILL_FRACTIONS["tictactoe"],
        )
    )


def get_trueskill_fractions(game_type_key: str) -> dict[str, float]:
    """
    Return ``sigma``, ``beta``, ``tau``, ``draw`` suitable for ``MU * value`` (except draw, used as-is).
    """
    from configuration.constants import MU

    try:
        from utils import database as database_module
        db = database_module.database
        if db is not None:
            game = db.get_game(game_type_key)
            if game is not None and game.rating_config:
                return {
                    "sigma": float(game.rating_config["sigma"]) / MU,
                    "beta": float(game.rating_config["beta"]) / MU,
                    "tau": float(game.rating_config["tau"]) / MU,
                    "draw": float(game.rating_config["draw"]),
                }
    except Exception:
        pass

    return get_seed_trueskill_fractions(game_type_key)
