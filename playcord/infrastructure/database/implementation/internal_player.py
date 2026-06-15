"""Internal player type used for Discord formatting."""

from __future__ import annotations

from playcord.core.player import Player


class InternalPlayer:
    """Internal player representation (IDs and strings only)."""

    def __init__(
        self,
        *,
        metadata: dict | None = None,
        user_id: int | None = None,
        username: str | None = None,
    ) -> None:
        self.name = username
        self.id = user_id
        self.metadata = metadata or {}
        self.servers: list = []
        self.player_data: dict = {}
        self.moves_made = 0
        self.is_bot = False
        self.bot_difficulty = None

    @property
    def display_name(self) -> str:
        """Human-readable player name for table rendering."""
        if self.is_bot:
            base = self.name or "Bot"
            if self.bot_difficulty:
                return f"{base} ({self.bot_difficulty})"
            return base
        if self.name:
            return f"@{str(self.name).lstrip('@')}"
        return f"@{self.id}"

    @property
    def mention(self) -> str:
        """Discord mention format or bot display name."""
        if self.is_bot:
            return self.name or "Bot"
        return f"<@{self.id}>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, InternalPlayer):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __str__(self) -> str:
        return f"InternalPlayer({self.id})"

    def __repr__(self) -> str:
        return f"InternalPlayer(id={self.id}, is_bot={self.is_bot})"


def internal_player_to_player(internal_player: InternalPlayer) -> Player:
    """Convert InternalPlayer to API Player object."""
    uid = internal_player.id
    uname = internal_player.name or (f"User {uid}" if uid is not None else "Unknown")
    return Player(
        id=uid,
        name=uname,
    )
