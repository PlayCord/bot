"""Fast lookups for who is in which matchmaking lobby."""

from __future__ import annotations

from typing import Any

from playcord import state as session_state

IN_MATCHMAKING = session_state.IN_MATCHMAKING


def matchmaking_by_user_id() -> dict[int, Any]:
    """Map Discord user id -> :class:`~utils.matchmaking_interface.MatchmakingInterface` (mirrors ``IN_MATCHMAKING`` keys)."""
    return {p.id: q for p, q in IN_MATCHMAKING.items()}
