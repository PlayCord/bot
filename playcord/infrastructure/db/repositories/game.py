"""Game metadata repository methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playcord.infrastructure.db.database import Database


@dataclass(slots=True)
class GameRepository:
    database: Database

    def get(self, game_name: str) -> Any | None:
        return self.database.get_game(game_name)

    def get_by_id(self, game_id: int) -> Any | None:
        return self.database.get_game_by_id(game_id)

    def list(self, *, active_only: bool = True) -> list[Any]:
        return self.database.get_all_games(active_only=active_only)

    def get_leaderboard(
        self,
        member_user_ids: list[int],
        game_id: int,
        *,
        limit: int = 10,
        offset: int = 0,
        min_matches: int = 5,
    ) -> list[dict[str, Any]]:
        return self.database.get_leaderboard(
            member_user_ids, game_id, limit=limit, offset=offset, min_matches=min_matches
        )

    def get_global_leaderboard(
        self,
        game_id: int,
        *,
        limit: int = 10,
        offset: int = 0,
        min_matches: int = 5,
    ) -> list[dict[str, Any]]:
        return self.database.get_global_leaderboard(
            game_id, limit=limit, offset=offset, min_matches=min_matches
        )
