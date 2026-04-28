"""Statistics service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playcord.application.repositories import MatchRepositoryPort, PlayerRepositoryPort


@dataclass(slots=True)
class StatsService:
    matches: MatchRepositoryPort
    players: PlayerRepositoryPort

    def history_for_user(self, user_id: int, *, limit: int = 20) -> list[Any]:
        return self.matches.get_history_for_user(user_id, limit=limit)
