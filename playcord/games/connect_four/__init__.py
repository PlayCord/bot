"""Connect Four plugin."""

from playcord.games.plugin import LegacyGamePlugin

plugin = LegacyGamePlugin(
    "connectfour", "playcord.games_impl.ConnectFour", "ConnectFourGame"
)

__all__ = ["plugin"]
