"""Shared interface helpers used across matchmaking and game modules."""

from typing import Any

from playcord.application.runtime_context import try_get_container


def _active_game_map() -> dict[Any, Any]:
    c = try_get_container()
    if c is not None:
        return c.registry.user_to_game
    return {}


def _active_matchmaking_map() -> dict[Any, Any]:
    c = try_get_container()
    if c is not None:
        return c.registry.user_to_matchmaking
    return {}


def _user_in_player_map(mapping: dict[Any, Any], user_id: int) -> bool:
    """True if any key in ``mapping`` is a user id or a player-like object with matching ``id``."""
    if user_id in mapping:
        return True
    for player in mapping:
        if getattr(player, "id", None) == user_id:
            return True
    return False


def user_in_active_game(user_id: int) -> bool:
    """Return True when the user is currently in any active game across all servers."""
    return _user_in_player_map(_active_game_map(), user_id)


def user_in_active_matchmaking(user_id: int) -> bool:
    """Return True when the user is currently queued in any active matchmaking lobby."""
    return _user_in_player_map(_active_matchmaking_map(), user_id)


def synthetic_bot_name_from_id(user_id: int) -> str:
    return f"Bot {str(user_id)[-4:]} (Bot)"


__all__ = [
    "user_in_active_game",
    "user_in_active_matchmaking",
    "synthetic_bot_name_from_id",
]
