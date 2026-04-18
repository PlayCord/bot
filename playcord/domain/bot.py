"""Bot difficulty metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BotDefinition:
    """Represents a bot difficulty configuration exposed by a game."""

    description: str
    callback: str | None = None
