"""Match and replay repository methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playcord.utils.database import Database


@dataclass(slots=True)
class MatchRepository:
    database: Database

    def get(self, match_id: int) -> Any | None:
        return self.database.get_match(match_id)

    def get_by_code(self, code: str) -> Any | None:
        return self.database.get_match_by_code(code)

    def update_status(
        self,
        match_id: int,
        status: str,
        *,
        metadata_patch: dict[str, Any] | None = None,
    ) -> None:
        self.database.update_match_status(
            match_id,
            status,
            metadata_patch=metadata_patch,
        )

    def get_history_for_user(self, user_id: int, *, limit: int = 20) -> list[Any]:
        return self.database.get_match_history_for_user(user_id, limit=limit)


@dataclass(slots=True)
class ReplayRepository:
    database: Database

    def get_events(self, match_id: int) -> list[dict[str, Any]]:
        return self.database.get_replay_events(match_id)

    def append_event(
        self,
        match_id: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        event: dict[str, Any] = {"type": event_type, **(payload or {})}
        self.database.append_replay_event(match_id, event)
