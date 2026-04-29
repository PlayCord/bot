"""Move repository (standalone helpers; match flows often use :class:`MatchRepository`)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from playcord.infrastructure.database.implementation.database import Database


@dataclass(slots=True)
class MoveRepository:
    database: Database

    def get_move_count(self, match_id: int) -> int:
        query = "SELECT COUNT(*) as count FROM match_moves WHERE match_id = %s AND is_deleted = FALSE;"
        result = self.database.execute_query(query, (match_id,), fetchone=True)
        return result["count"] if result else 0

    def record_move(
        self,
        match_id: int,
        user_id: int | None,
        move_number: int | None,
        move_data: dict[str, Any] | None = None,
        *,
        is_game_affecting: bool = True,
        kind: str = "move",
    ) -> None:
        move_json = json.dumps(move_data) if move_data else None
        query_next = """
            SELECT COALESCE(MAX(move_number), 0) + 1 as next_move_num
            FROM match_moves
            WHERE match_id = %s;
        """
        result = self.database.execute_query(query_next, (match_id,), fetchone=True)
        auto_sequence = result["next_move_num"] if result else 1
        query = """
            INSERT INTO match_moves
                (match_id, user_id, move_number, kind, move_data, game_state_after,
                 time_taken_ms, is_game_affecting)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s);
        """
        self.database.execute_query(
            query,
            (
                match_id,
                user_id,
                auto_sequence,
                kind,
                move_json,
                None,
                None,
                is_game_affecting,
            ),
        )
