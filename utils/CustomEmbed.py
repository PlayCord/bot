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


class ErrorEmbed(discord.Embed):

    def __init__(self, what_failed, reason):
        super().__init__(title="<a:facepalm:1328480069156606144> Something went wrong!", color=EMBED_COLOR)  # Force a consistent embed color based on the config

        self.add_field(name="<a:explosion:1328480397121683549> What failed?", value=what_failed, inline=False)
        self.add_field(name="<:hmm:1328480770846621757> Reason:", value=reason, inline=False)

        self.set_footer(text=f"Sorry for the inconvenience! Please report this issue on our GitHub page.")

