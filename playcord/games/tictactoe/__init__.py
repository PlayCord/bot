"""Tic-tac-toe plugin."""

from playcord.games.plugin import LegacyGamePlugin

plugin = LegacyGamePlugin("tictactoe", "playcord.games_impl.TicTacToe", "TicTacToeGame")

__all__ = ["plugin"]
