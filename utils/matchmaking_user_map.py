"""Fast lookups for who is in which matchmaking lobby."""

from __future__ import annotations

from typing import Any

from configuration.constants import IN_MATCHMAKING


def matchmaking_by_user_id() -> dict[int, Any]:
    """Map Discord user id -> :class:`~utils.interfaces.MatchmakingInterface` (mirrors ``IN_MATCHMAKING`` keys)."""
    return {p.id: q for p, q in IN_MATCHMAKING.items()}
