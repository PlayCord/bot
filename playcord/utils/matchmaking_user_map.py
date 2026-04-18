"""Fast lookups for who is in which matchmaking lobby."""

from __future__ import annotations

from typing import Any

from playcord import state as session_state

IN_MATCHMAKING = session_state.IN_MATCHMAKING


def matchmaking_by_user_id() -> dict[int, Any]:
    """Map Discord user id -> :class:`~utils.matchmaking_interface.MatchmakingInterface` (mirrors ``IN_MATCHMAKING`` keys)."""
    result: dict[int, Any] = {}
    for key, queue in IN_MATCHMAKING.items():
        if isinstance(key, int):
            result[key] = queue
            continue
        player_id = getattr(key, "id", None)
        if isinstance(player_id, int):
            result[player_id] = queue
    return result
