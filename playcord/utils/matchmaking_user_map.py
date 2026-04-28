"""Fast lookups for who is in which matchmaking lobby."""

from __future__ import annotations

from typing import Any

from playcord.application.runtime_context import try_get_container


def _matchmaking_map() -> dict[Any, Any]:
    c = try_get_container()
    if c is not None:
        return c.registry.user_to_matchmaking
    return {}


def matchmaking_by_user_id() -> dict[int, Any]:
    """Map Discord user id -> :class:`~utils.matchmaking_interface.MatchmakingInterface` (mirrors ``IN_MATCHMAKING`` keys)."""
    result: dict[int, Any] = {}
    for key, queue in _matchmaking_map().items():
        if isinstance(key, int):
            result[key] = queue
            continue
        player_id = getattr(key, "id", None)
        if isinstance(player_id, int):
            result[player_id] = queue
    return result
