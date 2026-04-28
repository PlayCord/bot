"""Match and replay repository methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playcord.infrastructure.db.database import Database


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

    def get_history_for_user(
        self,
        user_id: int,
        *,
        guild_id: int | None = None,
        game_id: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Any]:
        return self.database.get_user_match_history(
            user_id,
            guild_id,
            game_id=game_id,
            limit=limit,
            offset=offset,
        )

    def get_participants(self, match_id: int) -> list[Any]:
        return self.database.get_participants(match_id)

    def create_game(
        self,
        *,
        game_name: str,
        guild_id: int,
        participants: list[int],
        is_rated: bool = True,
        channel_id: int | None = None,
        thread_id: int | None = None,
        game_config: dict[str, Any] | None = None,
    ) -> tuple[int, str]:
        return self.database.create_game(
            game_name,
            guild_id,
            participants,
            is_rated=is_rated,
            channel_id=channel_id,
            thread_id=thread_id,
            game_config=game_config,
        )

    def update_match_context(
        self,
        match_id: int,
        *,
        channel_id: int | None = None,
        thread_id: int | None = None,
    ) -> None:
        self.database.update_match_context(
            match_id, channel_id=channel_id, thread_id=thread_id
        )

    def end_match(
        self,
        match_id: int,
        final_state: dict[str, Any],
        results: dict[int, dict[str, Any]],
    ) -> None:
        self.database.end_match(match_id, final_state, results)

    def merge_match_metadata_outcome_display(
        self,
        match_id: int,
        *,
        summaries: dict[int, str] | None = None,
        global_summary: str | None = None,
    ) -> None:
        self.database.merge_match_metadata_outcome_display(
            match_id, summaries=summaries, global_summary=global_summary
        )

    def get_match_human_user_ids_ordered(self, match_id: int) -> list[int]:
        return self.database.get_match_human_user_ids_ordered(match_id)

    def get_move_count(self, match_id: int) -> int:
        return self.database.get_move_count(match_id)

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
        self.database.record_move(
            match_id,
            user_id,
            move_number,
            move_data,
            is_game_affecting=is_game_affecting,
            kind=kind,
        )


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

    def append_replay_dict(self, match_id: int, event: dict[str, Any]) -> None:
        """Append a replay event dict as produced by runtime (includes ``type``)."""
        self.database.append_replay_event(match_id, event)
