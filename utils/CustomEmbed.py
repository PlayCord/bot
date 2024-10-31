import discord

from configuration.constants import EMBED_COLOR


class CustomEmbed(discord.Embed):
    def __init__(self, **kwargs):

        super().__init__(**kwargs, color=EMBED_COLOR)  # Force a consistent embed color based on the config

        self.set_footer(text=f"Made with ❤ by @quantumbagel",  # Force bagel footer by default, this can be overriden tho
                     icon_url="https://avatars.githubusercontent.com/u/58365715")


