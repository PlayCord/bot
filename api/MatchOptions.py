"""
Lobby customization before a match starts.

Games declare :attr:`api.Game.Game.customizable_options` as a tuple of :class:`MatchOptionSpec`.
Values are chosen in the matchmaking UI and passed to the game as ``match_options`` if it accepts them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class MatchOptionSpec:
    """
    One setting shown as a Discord string select on the lobby message.

    * ``kind="choices"``: use ``choices`` as (display label, stored value) pairs; ``default`` must match a value.
    * ``kind="int"``: integer from ``min_value``..``max_value`` inclusive; options are built as str(value).
    """

    key: str
    label: str
    kind: Literal["choices", "int"]
    default: str | int
    choices: tuple[tuple[str, str], ...] | None = None
    min_value: int | None = None
    max_value: int | None = None

    def __post_init__(self) -> None:
        if self.kind == "choices":
            if not self.choices:
                raise ValueError(f"MatchOptionSpec {self.key!r}: choices required")
            vals = {v for _, v in self.choices}
            if self.default not in vals:
                raise ValueError(f"MatchOptionSpec {self.key!r}: default not in choices")
        else:
            if self.min_value is None or self.max_value is None:
                raise ValueError(f"MatchOptionSpec {self.key!r}: min_value and max_value required for int")
            if self.min_value > self.max_value:
                raise ValueError(f"MatchOptionSpec {self.key!r}: min_value > max_value")
            span = self.max_value - self.min_value + 1
            if span > 25:
                raise ValueError(
                    f"MatchOptionSpec {self.key!r}: int range spans {span} options (Discord max 25)"
                )
            d = int(self.default)
            if d < self.min_value or d > self.max_value:
                raise ValueError(f"MatchOptionSpec {self.key!r}: default out of range")

    def allowed_values(self) -> set[str]:
        if self.kind == "choices":
            return {v for _, v in self.choices or ()}
        return {str(i) for i in range(self.min_value, self.max_value + 1)}

    def coerce(self, raw: str) -> str | int:
        """Validate Discord select string value; fall back to default."""
        if self.kind == "choices":
            if raw in self.allowed_values():
                return raw
            return str(self.default)
        try:
            v = int(raw)
        except ValueError:
            return int(self.default)
        if self.min_value <= v <= self.max_value:
            return v
        return int(self.default)

    def select_options(self) -> list[tuple[str, str, bool]]:
        """(label, value, is_default) for building discord.SelectOption."""
        if self.kind == "choices":
            cur = str(self.default)
            return [(lab, val, val == cur) for lab, val in (self.choices or ())]
        cur = int(self.default)
        out: list[tuple[str, str, bool]] = []
        for i in range(self.min_value, self.max_value + 1):
            out.append((str(i), str(i), i == cur))
        return out
