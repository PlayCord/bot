"""Shared interface helpers used across matchmaking and game modules."""

from playcord import state as session_state

IN_GAME = session_state.IN_GAME
IN_MATCHMAKING = session_state.IN_MATCHMAKING


def _user_in_player_map(mapping: dict, user_id: int) -> bool:
    """True if any key in ``mapping`` is a player-like object with matching ``id``."""
    for player in mapping:
        if getattr(player, "id", None) == user_id:
            return True
    return False


def user_in_active_game(user_id: int) -> bool:
    """Return True when the user is currently in any active game across all servers."""
    return _user_in_player_map(IN_GAME, user_id)


def user_in_active_matchmaking(user_id: int) -> bool:
    """Return True when the user is currently queued in any active matchmaking lobby."""
    return _user_in_player_map(IN_MATCHMAKING, user_id)


def synthetic_bot_name_from_id(user_id: int) -> str:
    return f"Bot {str(user_id)[-4:]} (Bot)"


__all__ = [
    "user_in_active_game",
    "user_in_active_matchmaking",
    "synthetic_bot_name_from_id",
]
