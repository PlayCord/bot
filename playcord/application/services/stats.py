"""Statistics service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playcord.infrastructure.database import MatchRepository, PlayerRepository


@dataclass(slots=True)
class StatsService:
    matches: MatchRepository
    players: PlayerRepository

    def history_for_user(self, user_id: int, *, limit: int = 20) -> list[Any]:
        return self.matches.get_history_for_user(user_id, limit=limit)
