"""Game-session orchestration service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playcord.infrastructure.database import (
        MatchRepository,
        PlayerRepository,
        ReplayRepository,
    )
    from playcord.infrastructure.state.user_games import SessionRegistry


@dataclass(slots=True)
class GameSessionService:
    """Coordinates active game sessions and replay/rating side effects."""

    registry: SessionRegistry
    matches: MatchRepository
    replays: ReplayRepository
    ratings: PlayerRepository

    def register(self, thread_id: int, session: Any) -> None:
        self.registry.games_by_thread_id[thread_id] = session
        for player in getattr(session, "players", []) or []:
            if getattr(player, "id", None) is not None:
                self.registry.user_to_game[int(player.id)] = session

    def register_runtime(self, runtime: Any) -> None:
        thread = getattr(runtime, "thread", None)
        thread_id = getattr(thread, "id", None)
        if thread_id is None:
            msg = "runtime thread is not ready yet"
            raise ValueError(msg)
        self.register(int(thread_id), runtime)

    def unregister(self, thread_id: int) -> None:
        session = self.registry.games_by_thread_id.pop(thread_id, None)
        self.registry.discard_thread_cache(thread_id)
        if session is None:
            return
        for player in getattr(session, "players", []) or []:
            player_id = getattr(player, "id", None)
            if player_id is not None:
                self.registry.user_to_game.pop(int(player_id), None)

    def get(self, thread_id: int) -> Any | None:
        return self.registry.games_by_thread_id.get(thread_id)

    def by_user_id(self, user_id: int) -> Any | None:
        return self.registry.user_to_game.get(user_id)
