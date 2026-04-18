"""Game-session orchestration service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playcord.application.services.session_registry import SessionRegistry


@dataclass(slots=True)
class GameSessionService:
    """Coordinates active game sessions and replay/rating side effects."""

    registry: SessionRegistry
    matches: Any
    replays: Any
    ratings: Any

    def register(self, thread_id: int, session: Any) -> None:
        self.registry.games_by_thread_id[thread_id] = session
        for player in getattr(session, "players", []) or []:
            if getattr(player, "id", None) is not None:
                self.registry.user_to_game[int(player.id)] = session

    def unregister(self, thread_id: int) -> None:
        session = self.registry.games_by_thread_id.pop(thread_id, None)
        if session is None:
            return
        for player in getattr(session, "players", []) or []:
            player_id = getattr(player, "id", None)
            if player_id is not None:
                self.registry.user_to_game.pop(int(player_id), None)

    def get(self, thread_id: int) -> Any | None:
        return self.registry.games_by_thread_id.get(thread_id)
