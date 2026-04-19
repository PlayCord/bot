"""
Resolve TrueSkill parameters for a game type key.

Runtime reads come from ``games.rating_config`` in the database. This module keeps a
small DB-first resolver with a ``Game``-class fallback for startup/bootstrap.
"""

from __future__ import annotations

from playcord.domain.rating import DEFAULT_TRUESKILL_PARAMETERS
from playcord.games import PLUGIN_BY_KEY
from playcord.utils.logging_config import get_logger

log = get_logger("trueskill")


def get_seed_trueskill_parameters(game_type_key: str) -> dict[str, float]:
    """Bootstrap/default TrueSkill parameters before the DB-backed game registry is available."""
    plugin = PLUGIN_BY_KEY.get(game_type_key)
    if plugin is None:
        return dict(DEFAULT_TRUESKILL_PARAMETERS)
    try:
        return dict(
            plugin.metadata().trueskill_parameters or DEFAULT_TRUESKILL_PARAMETERS
        )
    except (AttributeError, ImportError, TypeError, ValueError) as exc:
        log.warning(
            "Failed to load seed TrueSkill parameters for %s: %s",
            game_type_key,
            exc,
        )
        return dict(DEFAULT_TRUESKILL_PARAMETERS)


def get_trueskill_parameters(game_type_key: str) -> dict[str, float]:
    """
    Return ``sigma``, ``beta``, ``tau``, ``draw`` suitable for ``MU * value`` (except draw, used as-is).
    """
    from playcord.infrastructure.app_constants import MU

    try:
        from playcord.utils import database as database_module

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
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        log.warning(
            "Falling back to seed TrueSkill parameters for %s: %s",
            game_type_key,
            exc,
        )

    return get_seed_trueskill_parameters(game_type_key)
