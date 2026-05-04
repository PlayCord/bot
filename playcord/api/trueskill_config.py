"""Resolve TrueSkill parameters for a game type key.

Runtime reads come from ``games.rating_config`` in the database. This module keeps a
small DB-first resolver with a ``Game``-class fallback for startup/bootstrap.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from playcord.core.rating import DEFAULT_TRUESKILL_PARAMETERS
from playcord.games import GAME_BY_KEY
from playcord.infrastructure.logging import get_logger

log = get_logger("trueskill")
RatingConfigProvider = Callable[[str], Mapping[str, float] | None]
_rating_config_provider: RatingConfigProvider | None = None


def bind_rating_config_provider(provider: RatingConfigProvider | None) -> None:
    """Bind a process-wide provider for DB-backed TrueSkill config lookup."""
    global _rating_config_provider
    _rating_config_provider = provider


def get_seed_trueskill_parameters(game_type_key: str) -> dict[str, float]:
    """Bootstrap/default TrueSkill parameters before DB-backed registry exists."""
    game = GAME_BY_KEY.get(game_type_key)
    if game is None:
        return dict(DEFAULT_TRUESKILL_PARAMETERS)
    try:
        return dict(
            game.metadata().trueskill_parameters or DEFAULT_TRUESKILL_PARAMETERS,
        )
    except (AttributeError, ImportError, TypeError, ValueError) as exc:
        log.warning(
            "Failed to load seed TrueSkill parameters for %s: %s",
            game_type_key,
            exc,
        )
        return dict(DEFAULT_TRUESKILL_PARAMETERS)


def get_trueskill_parameters(game_type_key: str) -> dict[str, float]:
    """Return ``sigma``, ``beta``, ``tau``, ``draw`` scaled by ``STARTING_RATING``."""
    from playcord.core.rating import STARTING_RATING

    try:
        if _rating_config_provider is not None:
            config = _rating_config_provider(game_type_key)
            if config:
                return {
                    "sigma": float(config["sigma"]) / STARTING_RATING,
                    "beta": float(config["beta"]) / STARTING_RATING,
                    "tau": float(config["tau"]) / STARTING_RATING,
                    "draw": float(config["draw"]),
                }
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        log.warning(
            "Falling back to seed TrueSkill parameters for %s: %s",
            game_type_key,
            exc,
        )

    return get_seed_trueskill_parameters(game_type_key)
