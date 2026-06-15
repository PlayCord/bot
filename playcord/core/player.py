"""Canonical player model for PlayCord."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

BOT_ID_BASE = 9_000_000_000_000


@dataclass(slots=True)
class Player:
    """A player participating in a game."""

    id: int | str
    display_name: str | None = None
    is_bot: bool = False
    bot_difficulty: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    player_data: dict[str, Any] = field(default_factory=dict)
    ranking: int | None = None

    @property
    def mention(self) -> str:
        if self.is_bot:
            base = self.display_name or "Bot"
            if self.bot_difficulty:
                return f"{base} ({self.bot_difficulty})"
            return base
        return f"<@{self.id}>"

    @property
    def name(self) -> str | None:
        return self.display_name

    @classmethod
    def create_bot(
        cls,
        name: str,
        difficulty: str,
        *,
        bot_index: int = 0,
    ) -> Player:
        return cls(
            id=BOT_ID_BASE + bot_index,
            display_name=name,
            is_bot=True,
            bot_difficulty=difficulty,
        )

    @classmethod
    def from_legacy(cls, legacy: Any) -> Player:
        """Create a canonical player from either legacy player model."""
        display_name = getattr(legacy, "display_name", None) or getattr(
            legacy,
            "name",
            None,
        )
        return cls(
            id=legacy.id,
            display_name=display_name,
            is_bot=bool(getattr(legacy, "is_bot", False)),
            bot_difficulty=getattr(legacy, "bot_difficulty", None),
            metadata=dict(getattr(legacy, "metadata", {}) or {}),
            player_data=dict(getattr(legacy, "player_data", {}) or {}),
            ranking=getattr(legacy, "ranking", None),
        )
