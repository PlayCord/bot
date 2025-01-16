import discord

from configuration.constants import EMBED_COLOR
from utils.conversion import contextify


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

    def __init__(self, ctx, what_failed, reason):
        super().__init__(title="<a:facepalm:1328480069156606144> Something went wrong!", color=EMBED_COLOR)  # Force a consistent embed color based on the config
        self.add_field(name="<:github:1329546977377259692> Please report the issue on GitHub",
                       value="I would really appreciate if you reported this error (and a detailed description of what you did to cause it if possible) on the [GitHub issue tracker](https://github.com/quantumbagel/PlayCord/issues)")
        self.add_field(name="<:clueless:1329547266087718975> Context:", value=contextify(ctx), inline=False)
        self.add_field(name="<a:explosion:1328480397121683549> What failed?", value="```"+what_failed+"```", inline=False)
        text_fields = []
        running_total = 0
        temp_line = ""
        for line in reason.split("\n"):
            running_total += len(line)
            if running_total <= 1018:
                temp_line += line
            else:
                text_fields.append(temp_line)
                temp_line = line
                running_total = len(line)
        text_fields.append(temp_line)

        for i in range(len(text_fields)):
            self.add_field(name="<:hmm:1328480770846621757> Reason:", value="```"+text_fields[i]+"```", inline=False)

        self.set_footer(text=f"Sorry for the inconvenience! Please report this issue on our GitHub page.")

