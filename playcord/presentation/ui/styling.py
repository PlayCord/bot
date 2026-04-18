"""Shared UI styling values."""

from __future__ import annotations

from dataclasses import dataclass

import discord


@dataclass(frozen=True, slots=True)
class Palette:
    primary: discord.Color = discord.Color.from_str("#6877ED")
    error: discord.Color = discord.Color.from_str("#ED6868")
    info: discord.Color = discord.Color.from_str("#9A9CB0")
    success: discord.Color = discord.Color.from_str("#68ED7B")
    warning: discord.Color = discord.Color.from_str("#EDC868")
    game: discord.Color = discord.Color.from_str("#68D4ED")
    matchmaking: discord.Color = discord.Color.from_str("#B068ED")


PALETTE = Palette()
