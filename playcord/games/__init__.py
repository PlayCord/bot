"""Explicit game plugin registry."""

from playcord.games.connect_four import plugin as connect_four_plugin
from playcord.games.nim import plugin as nim_plugin
from playcord.games.tictactoe import plugin as tictactoe_plugin

PLUGINS = [
    tictactoe_plugin,
    connect_four_plugin,
    nim_plugin,
]

PLUGIN_BY_KEY = {plugin.key: plugin for plugin in PLUGINS}

__all__ = ["PLUGINS", "PLUGIN_BY_KEY"]
