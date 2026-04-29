"""Bot difficulty metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playcord.api.handlers import HandlerSpec


@dataclass(frozen=True, slots=True)
class BotDefinition:
    """Represents a bot difficulty configuration exposed by a game."""

    description: str
    callback: HandlerSpec = None
