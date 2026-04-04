"""
Resolve TrueSkill sigma/beta/tau/draw fractions for a game type key.

Uses the concrete :class:`api.Game.Game` subclass when registered in ``GAME_TYPES``,
otherwise falls back to :data:`configuration.constants.GAME_TRUESKILL`.
"""

from __future__ import annotations

import importlib
from typing import Any


def get_trueskill_fractions(game_type_key: str) -> dict[str, float]:
    """
    Return ``sigma``, ``beta``, ``tau``, ``draw`` suitable for ``MU * value`` (except draw, used as-is).

    Class attribute ``trueskill_scale`` on the game class overrides keys from the global table.
    """
    from api.Game import Game
    from configuration.constants import GAME_TYPES, GAME_TRUESKILL

    spec = GAME_TYPES.get(game_type_key)
    if spec:
        mod_name, cls_name = spec
        try:
            mod = importlib.import_module(mod_name)
            cls = getattr(mod, cls_name)
            if isinstance(cls, type) and issubclass(cls, Game):
                return cls.trueskill_fractions(game_type_key)
        except Exception:
            pass
    base = GAME_TRUESKILL.get(game_type_key, GAME_TRUESKILL["tictactoe"])
    return dict(base)
