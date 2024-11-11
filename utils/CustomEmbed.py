import discord

from configuration.constants import EMBED_COLOR


class CustomEmbed(discord.Embed):
    """
    A modified version of discord.Embed with two key changes:

    * respects the default embed color of constants.py
    * Adds a bagel footer by default
    """
    def __init__(self, **kwargs):
        """
        Initialize the embed.
        :param kwargs: Arguments to the discord.Embed constructor
        """
        super().__init__(**kwargs, color=EMBED_COLOR)  # Force a consistent embed color based on the config

        self.set_footer(text=f"Made with ❤ by @quantumbagel",  # Force bagel footer by default, this can be overriden tho
                     icon_url="https://avatars.githubusercontent.com/u/58365715")


