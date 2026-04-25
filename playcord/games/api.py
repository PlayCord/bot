"""Final game plugin API used by GameRuntime."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from playcord.domain.game import GameMetadata
from playcord.domain.match_options import MatchOptionSpec
from playcord.domain.player import Player

ButtonStyle = Literal["primary", "secondary", "success", "danger"]
MessageTarget = Literal["thread", "overview", "ephemeral"]
MessagePurpose = Literal[
    "board",
    "announcement",
    "ephemeral",
    "custom",
    "overview",
]
OutcomeKind = Literal["winner", "draw", "interrupted"]


@dataclass(frozen=True, slots=True)
class ButtonSpec:
    label: str | None = None
    action_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    style: ButtonStyle = "secondary"
    emoji: str | None = None
    disabled: bool = False
    require_current_turn: bool = True


@dataclass(frozen=True, slots=True)
class SelectChoice:
    label: str
    value: str
    default: bool = False


@dataclass(frozen=True, slots=True)
class SelectSpec:
    action_name: str
    options: tuple[SelectChoice, ...]
    placeholder: str | None = None
    disabled: bool = False
    require_current_turn: bool = True


@dataclass(frozen=True, slots=True)
class BinaryAsset:
    filename: str
    data: bytes
    description: str | None = None


@dataclass(frozen=True, slots=True)
class MessageLayout:
    content: str | None = None
    buttons: tuple[ButtonSpec, ...] = ()
    selects: tuple[SelectSpec, ...] = ()
    attachments: tuple[BinaryAsset, ...] = ()
    # When set, buttons are grouped into discord.ui.ActionRow chunks of this width (e.g. 3 for a grid).
    button_row_width: int | None = None


@dataclass(frozen=True, slots=True)
class ChannelAction:
    target: MessageTarget


@dataclass(frozen=True, slots=True)
class UpsertMessage(ChannelAction):
    key: str
    layout: MessageLayout
    purpose: MessagePurpose = "custom"


@dataclass(frozen=True, slots=True)
class DeleteMessage(ChannelAction):
    key: str


@dataclass(frozen=True, slots=True)
class Outcome:
    kind: OutcomeKind
    placements: list[list[Player]] = field(default_factory=list)
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ReplayState:
    game_key: str
    players: list[Player]
    match_options: dict[str, Any]
    move_index: int
    state: Any


@dataclass(frozen=True, slots=True)
class OwnedMessage:
    key: str
    purpose: str
    discord_message_id: int
    channel_id: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GameContext:
    match_id: int
    game_key: str
    players: list[Player]
    match_options: dict[str, Any]
    owned_messages: list[OwnedMessage] = field(default_factory=list)
    latest_overview: str | None = None

    def get_message(self, discord_message_id: int) -> OwnedMessage | None:
        for message in self.owned_messages:
            if message.discord_message_id == discord_message_id:
                return message
        return None

    def list_owned_messages(self, *, purpose: str | None = None) -> list[OwnedMessage]:
        if purpose is None:
            return list(self.owned_messages)
        return [
            message for message in self.owned_messages if message.purpose == purpose
        ]


class GamePlugin(ABC):
    """Stateful plugin instance managed by GameRuntime."""

    metadata: GameMetadata

    def __init__(
        self,
        players: list[Player],
        *,
        match_options: dict[str, Any] | None = None,
    ) -> None:
        self.players = players
        self.match_options = dict(match_options or {})
        # Wired by ``GameRuntime`` for ``log_replay_event`` → ``replay_events``.
        self._replay_hook: Callable[[str, dict[str, Any]], None] | None = None

    @classmethod
    def option_specs(cls) -> tuple[MatchOptionSpec, ...]:
        return tuple(getattr(cls.metadata, "customizable_options", ()) or ())

    @abstractmethod
    def current_turn(self) -> Player | None:
        """Return the player whose turn it is."""

    @abstractmethod
    def outcome(self) -> Outcome | None:
        """Return the current outcome, if any."""

    @abstractmethod
    def render(self, ctx: GameContext) -> tuple[ChannelAction, ...]:
        """Render the current board/state."""

    def match_global_summary(self, outcome: Outcome) -> str | None:
        return None

    def match_summary(self, outcome: Outcome) -> dict[int, str] | None:
        return None

    def initial_replay_state(self, ctx: GameContext) -> ReplayState | None:
        return None

    def apply_replay_event(
        self, state: ReplayState, event: dict[str, Any]
    ) -> ReplayState | None:
        return None

    def render_replay(self, state: ReplayState) -> MessageLayout | None:
        return None

    def log_replay_event(self, event_type: str, **payload: Any) -> None:
        """Append a replay row when ``_replay_hook`` is set (by ``GameRuntime``)."""
        hook = self._replay_hook
        if hook is not None:
            hook(event_type, payload)
