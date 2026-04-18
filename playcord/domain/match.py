"""Match-level data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from playcord.domain.player import Player


class MatchOutcomeKind(str, Enum):
    in_progress = "in_progress"
    winner = "winner"
    draw = "draw"
    interrupted = "interrupted"


@dataclass(frozen=True, slots=True)
class Seat:
    """One seated participant in a match."""

    index: int
    player: Player
    role: str | None = None


@dataclass(slots=True)
class MatchOutcome:
    """Normalized match outcome model."""

    kind: MatchOutcomeKind
    placements: list[list[Player]] = field(default_factory=list)
    summary: str | None = None
