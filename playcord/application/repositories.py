"""Repository protocols consumed by application services."""

from __future__ import annotations

from typing import Any, Protocol


class PlayerRepositoryPort(Protocol):
    def get(self, user_id: int) -> Any | None: ...

    def upsert(self, user_id: int, username: str, *, is_bot: bool = False) -> None: ...

    def get_discord_player(self, user: Any, guild_id: int) -> Any | None: ...

    def get_user_all_ratings(self, user_id: int) -> list[Any]: ...

    def get_user_global_rank(self, user_id: int, game_id: int) -> int | None: ...

    def get_rating_history(
        self,
        user_id: int,
        guild_id: int | None,
        game_id: int,
        *,
        days: int = 30,
    ) -> list[dict[str, Any]]: ...

    def get_preferences(self, user_id: int) -> dict[str, Any] | None: ...

    def update_preferences(self, user_id: int, preferences: dict[str, Any]) -> None: ...


class GameRepositoryPort(Protocol):
    def get(self, game_name: str) -> Any | None: ...

    def get_by_id(self, game_id: int) -> Any | None: ...

    def list(self, *, active_only: bool = True) -> list[Any]: ...

    def get_leaderboard(
        self,
        member_user_ids: list[int],
        game_id: int,
        *,
        limit: int = 10,
        offset: int = 0,
        min_matches: int = 5,
    ) -> list[dict[str, Any]]: ...

    def get_global_leaderboard(
        self,
        game_id: int,
        *,
        limit: int = 10,
        offset: int = 0,
        min_matches: int = 5,
    ) -> list[dict[str, Any]]: ...


class MatchRepositoryPort(Protocol):
    def get(self, match_id: int) -> Any | None: ...

    def get_by_code(self, code: str) -> Any | None: ...

    def get_history_for_user(
        self,
        user_id: int,
        *,
        guild_id: int | None = None,
        game_id: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Any]: ...

    def get_participants(self, match_id: int) -> list[Any]: ...

    def update_status(
        self,
        match_id: int,
        status: str,
        *,
        metadata_patch: dict[str, Any] | None = None,
    ) -> None: ...

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
    ) -> tuple[int, str]: ...

    def update_match_context(
        self,
        match_id: int,
        *,
        channel_id: int | None = None,
        thread_id: int | None = None,
    ) -> None: ...

    def end_match(
        self,
        match_id: int,
        final_state: dict[str, Any],
        results: dict[int, dict[str, Any]],
    ) -> None: ...

    def merge_match_metadata_outcome_display(
        self,
        match_id: int,
        *,
        summaries: dict[int, str] | None = None,
        global_summary: str | None = None,
    ) -> None: ...

    def get_match_human_user_ids_ordered(self, match_id: int) -> list[int]: ...

    def get_move_count(self, match_id: int) -> int: ...

    def record_move(
        self,
        match_id: int,
        user_id: int | None,
        move_number: int | None,
        move_data: dict[str, Any] | None = None,
        *,
        is_game_affecting: bool = True,
        kind: str = "move",
    ) -> None: ...


class ReplayRepositoryPort(Protocol):
    def get_events(self, match_id: int) -> list[dict[str, Any]]: ...

    def append_event(
        self,
        match_id: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> None: ...

    def append_replay_dict(self, match_id: int, event: dict[str, Any]) -> None: ...


class AnalyticsRepositoryPort(Protocol):
    def record_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None: ...

    def get_summary(self, *, hours: int = 24) -> list[dict[str, Any]]: ...

    def get_recent_events(self, *, hours: int = 24, limit: int = 50) -> list[Any]: ...

    def get_event_counts_by_game(self, *, hours: int = 24) -> list[dict[str, Any]]: ...


class GuildRepositoryPort(Protocol):
    """Guild settings and destructive admin maintenance."""

    def merge_settings(self, guild_id: int, patch: dict[str, Any]) -> None: ...

    def get_playcord_channel_id(self, guild_id: int) -> int | None: ...

    def delete_guild(self, guild_id: int) -> None: ...

    def cleanup_old_analytics(self, days: int | None = None) -> int: ...

    def reset_all_data(self) -> None: ...

    def reset_game_data(self, game_id: int) -> Any: ...

    def reset_user_data(self, user_id: int) -> None: ...

    def reset_guild_data(self, guild_id: int) -> None: ...
