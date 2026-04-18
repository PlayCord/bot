"""Explicit game plugin registry."""

from playcord.games.tictactoe import plugin as tictactoe_plugin

PLUGINS = [
    tictactoe_plugin,
]

PLUGIN_BY_KEY = {plugin.key: plugin for plugin in PLUGINS}

__all__ = ["PLUGINS", "PLUGIN_BY_KEY"]
