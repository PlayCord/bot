"""Nim plugin."""

from playcord.games.plugin import LegacyGamePlugin

plugin = LegacyGamePlugin("nim", "playcord.games_impl.Nim", "NimGame")

__all__ = ["plugin"]
