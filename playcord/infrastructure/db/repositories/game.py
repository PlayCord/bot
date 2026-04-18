"""Game metadata repository methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playcord.utils.database import Database


@dataclass(slots=True)
class GameRepository:
    database: Database

    def get(self, game_name: str) -> Any | None:
        return self.database.get_game(game_name)

    def get_by_id(self, game_id: int) -> Any | None:
        return self.database.get_game_by_id(game_id)

    def list(self, *, active_only: bool = True) -> list[Any]:
        return self.database.get_all_games(active_only=active_only)
