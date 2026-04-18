"""Matchmaking orchestration service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playcord.application.services.session_registry import SessionRegistry


@dataclass(slots=True)
class MatchmakingService:
    """Tracks active matchmaking sessions."""

    registry: SessionRegistry

    def register(self, message_id: int, lobby: Any) -> None:
        self.registry.matchmaking_by_message_id[message_id] = lobby
        for player in getattr(lobby, "players", []) or []:
            player_id = getattr(player, "id", None)
            if player_id is not None:
                self.registry.user_to_matchmaking[int(player_id)] = lobby

    def unregister(self, message_id: int) -> None:
        lobby = self.registry.matchmaking_by_message_id.pop(message_id, None)
        if lobby is None:
            return
        for player in getattr(lobby, "players", []) or []:
            player_id = getattr(player, "id", None)
            if player_id is not None:
                self.registry.user_to_matchmaking.pop(int(player_id), None)

    def by_user_id(self, user_id: int) -> Any | None:
        return self.registry.user_to_matchmaking.get(user_id)
