"""
Resolve TrueSkill parameters for a game type key.

Runtime reads come from ``games.rating_config`` in the database. This module keeps a
small DB-first resolver with a ``Game``-class fallback for startup/bootstrap.
"""

from __future__ import annotations


def get_seed_trueskill_parameters(game_type_key: str) -> dict[str, float]:
    """Bootstrap/default TrueSkill parameters before the DB-backed game registry is available."""
    from api.Game import Game
    from configuration.constants import GAME_TYPES

    spec = GAME_TYPES.get(game_type_key)
    if spec:
        try:
            _, cls_name = spec
            mod = __import__(spec[0], fromlist=[cls_name])
            cls = getattr(mod, cls_name)
            if isinstance(cls, type) and issubclass(cls, Game):
                return dict(
                    getattr(cls, "trueskill_parameters", None)
                    or Game.default_trueskill_parameters
                )
        except Exception:
            pass
    return dict(Game.default_trueskill_parameters)


def get_trueskill_parameters(game_type_key: str) -> dict[str, float]:
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

    return get_seed_trueskill_parameters(game_type_key)
