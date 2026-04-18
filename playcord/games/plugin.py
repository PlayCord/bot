"""Plugin registry helpers for the final game API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Type

from playcord.domain.game import GameMetadata, PlayerOrder, RoleMode
from playcord.games.api import GamePlugin


def resolve_player_count(game_class: type[GamePlugin]) -> int | list[int] | None:
    player_count = game_class.metadata.player_count
    if isinstance(player_count, int):
        return player_count
    if isinstance(player_count, tuple):
        return list(player_count)
    return None


@dataclass(frozen=True, slots=True)
class RegisteredGamePlugin:
    key: str
    game_class: Type[GamePlugin]

    @property
    def module_name(self) -> str:
        return self.game_class.__module__

    @property
    def class_name(self) -> str:
        return self.game_class.__name__

    def load(self) -> type[GamePlugin]:
        return self.game_class

    def metadata(self) -> GameMetadata:
        return self.game_class.metadata


__all__ = [
    "GamePlugin",
    "PlayerOrder",
    "RegisteredGamePlugin",
    "RoleMode",
    "resolve_player_count",
]
