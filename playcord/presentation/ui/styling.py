"""Shared UI styling values."""

from __future__ import annotations

from dataclasses import dataclass, field

import discord


def _color(hex_value: str) -> discord.Color:
    return discord.Color.from_str(hex_value)


@dataclass(frozen=True, slots=True)
class Palette:
    primary: discord.Color | None = None
    error: discord.Color = field(default_factory=lambda: _color("#ED6868"))
    info: discord.Color | None = None
    success: discord.Color = field(default_factory=lambda: _color("#68ED7B"))
    warning: discord.Color = field(default_factory=lambda: _color("#EDC868"))
    game: discord.Color | None = None
    matchmaking: discord.Color | None = None


PALETTE = Palette()
