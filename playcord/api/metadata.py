"""Game abstractions and metadata."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from collections.abc import Iterable, Sized
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar

from playcord.api.bot import BotDefinition
from playcord.api.handlers import HandlerSpec
from playcord.api.match_options import MatchOptionSpec
from playcord.core.errors import ConfigurationError
from playcord.core.player import Player
from playcord.core.rating import (
    DEFAULT_TRUESKILL_PARAMETERS,
    merge_trueskill_parameters,
)
from playcord.core.replay import ReplayEvent, ReplayRecorder


class ParameterKind(StrEnum):
    string = "string"
    integer = "integer"
    dropdown = "dropdown"


@dataclass(frozen=True, slots=True)
class MoveParameter:
    """Typed command parameter metadata."""

    name: str
    description: str
    kind: ParameterKind
    optional: bool = False
    autocomplete: HandlerSpec = None
    force_reload: bool = False
    choices: tuple[tuple[str, str], ...] | None = None
    min_value: int | None = None
    max_value: int | None = None


@dataclass(frozen=True, slots=True)
class Move:
    """A player-triggered action exposed as an app command."""

    name: str
    description: str
    options: tuple[MoveParameter, ...] = ()
    require_current_turn: bool = True
    callback: HandlerSpec = None
    is_game_affecting: bool = True


class PlayerOrder(StrEnum):
    random = "random"
    preserve = "preserve"
    creator_first = "creator_first"
    reverse = "reverse"


class RoleMode(StrEnum):
    none = "none"
    random = "random"
    chosen = "chosen"
    secret = "secret"


@dataclass(frozen=True, slots=True)
class GameMetadata:
    """Display and configuration metadata for a game plugin."""

    key: str
    name: str
    summary: str
    description: str
    move_group_description: str
    player_count: int | tuple[int, ...]
    author: str
    version: str
    author_link: str
    source_link: str
    time: str
    difficulty: str
    bots: dict[str, BotDefinition] = field(default_factory=dict)
    moves: tuple[Move, ...] = ()
    peek_callback: HandlerSpec = None
    player_order: PlayerOrder = PlayerOrder.random
    role_mode: RoleMode = RoleMode.none
    player_roles: tuple[str, ...] | None = None
    trueskill_parameters: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_TRUESKILL_PARAMETERS),
    )
    customizable_options: tuple[MatchOptionSpec, ...] = ()


class Game(ABC):
    """Pure game state and rules. Presentation belongs elsewhere."""

    metadata: ClassVar[GameMetadata]

    def __init__(self, players: list[Player]) -> None:
        self.players = players
        self._replay_recorder: ReplayRecorder | None = None

    @classmethod
    def required_player_count(cls) -> int | tuple[int, ...]:
        return cls.metadata.player_count

    @classmethod
    def supports_bots(cls) -> bool:
        return bool(cls.metadata.bots)

    @classmethod
    def get_trueskill_parameters(cls) -> dict[str, float]:
        return merge_trueskill_parameters(cls.metadata.trueskill_parameters)

    @classmethod
    def validate_role_selection(cls, selections: dict[int, str]) -> bool | str:
        roles = cls.metadata.player_roles
        if not roles:
            return True
        if (
            not isinstance(selections, dict)
            or not isinstance(roles, Iterable)
            or not isinstance(roles, Sized)
            or len(selections) != len(roles)
        ):
            return "Each player must choose a role."
        expected = Counter(list(roles))
        chosen = Counter(selections.values())
        if expected != chosen:
            return "Each role must be picked exactly once."
        return True

    @classmethod
    def seat_players(
        cls,
        players: list[Player],
        selections: dict[int, str] | None = None,
    ) -> list[Player]:
        ordered = list(players)
        roles = cls.metadata.player_roles
        if not roles or len(roles) != len(ordered):
            return ordered

        if cls.metadata.role_mode == RoleMode.none:
            return ordered

        if cls.metadata.role_mode == RoleMode.chosen:
            if not selections:
                return ordered
            by_id = {player.id: player for player in ordered}
            pools: defaultdict[str, list[Player]] = defaultdict(list)
            for player_id, role_key in selections.items():
                player = by_id.get(player_id)
                if player is not None:
                    pools[role_key].append(player)
            for key in pools:
                pools[key].sort(key=lambda player: str(player.id))
            try:
                return [pools[role].pop(0) for role in roles]
            except IndexError:
                return ordered

        if cls.metadata.role_mode in {RoleMode.random, RoleMode.secret}:
            random.shuffle(ordered)
            return ordered

        return ordered

    def attach_replay_recorder(self, recorder: ReplayRecorder | None) -> None:
        self._replay_recorder = recorder

    def log_replay_event(self, event_type: str, **payload: Any) -> None:
        if self._replay_recorder is None:
            return
        self._replay_recorder.record(ReplayEvent(type=event_type, payload=payload))

    def is_finished(self) -> bool:
        return self.outcome() is not None

    def match_global_summary(self, outcome: object) -> str | None:
        return None

    def match_summary(self, outcome: object) -> dict[int | str, str] | None:
        return None

    @abstractmethod
    def current_turn(self) -> Player:
        """Return the player whose turn it is."""

    @abstractmethod
    def outcome(self) -> Player | list[list[Player]] | str | None:
        """Return the current game outcome."""


def ensure_valid_player_count(game: type[Game], count: int) -> None:
    """Validate a player count against a game's metadata."""
    allowed = game.required_player_count()
    if isinstance(allowed, int):
        if count != allowed:
            raise ConfigurationError(
                f"{game.metadata.key} requires exactly {allowed} players",
            )
        return
    if count not in allowed:
        values = ", ".join(str(value) for value in allowed)
        raise ConfigurationError(
            f"{game.metadata.key} requires one of these player counts: {values}",
        )
