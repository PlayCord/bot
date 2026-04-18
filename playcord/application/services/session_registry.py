"""In-memory session registry replacing module-level globals."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SessionRegistry:
    """Tracks active games and matchmaking sessions."""

    games_by_thread_id: dict[int, Any] = field(default_factory=dict)
    matchmaking_by_message_id: dict[int, Any] = field(default_factory=dict)
    user_to_game: dict[int, Any] = field(default_factory=dict)
    user_to_matchmaking: dict[int, Any] = field(default_factory=dict)

    def reset(self) -> None:
        self.games_by_thread_id.clear()
        self.matchmaking_by_message_id.clear()
        self.user_to_game.clear()
        self.user_to_matchmaking.clear()
