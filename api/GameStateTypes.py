import io
from typing import Callable
from emoji import is_emoji
import discord
from discord import ButtonStyle

from utils.Player import Player


class GameStateType:
    def __init__(self):
        pass


class FieldType:
    def __init__(self, name, value, inline):
        self.name = name
        self.value = value
        self.inline = inline
        self.type = "field"
        self.limit = 25

    def _embed_transform(self, embed):
        embed.add_field(name=self.name, value=self.value, inline=self.inline)

class InfoRows:
    def __init__(self, data):


        self.data = data
        self.type = "info_rows"
        self.limit = 1

    def _embed_transform(self, embed):

        column = {}
        for person in self.data:
            for data_type in self.data[person]:
                if data_type not in column:
                    column[data_type] = {person: str(self.data[person][data_type])}
                column[data_type].update({person: str(self.data[person][data_type])})

        for data_type in column:
            for person in self.data:
                if person not in column[data_type]:
                    column[data_type].update({person: ""})
        number_names = 0
        for index in range((len(column)+(len(column)+1)//2)):


            if index % 3 == 0:

                embed.add_field(name="Name:", value="\n".join([str(p) for p in self.data.keys()]))
                number_names += 1
            else:
                embed.add_field(name=list(column.keys())[index - number_names], value="\n".join(column[list(column.keys())[index - number_names]].values()))



class ImageType:
    def __init__(self, bytes):
        self.limit = 1
        self.bytes = bytes
        self.type = "image"
        image = io.BytesIO()
        image.write(self.bytes)
        image.seek(0)
        self.game_picture = discord.File(image, filename="image.png")

    def _embed_transform(self, embed):
        # Add players and image to the embed
        embed.set_image(url="attachment://image.png")

class FooterType:

    def __init__(self, text):
        self.type = "footer"
        self.text = text
        self.limit = 1

    def _embed_transform(self, embed):
        embed.set_footer(text=self.text)


class ButtonType:
    """

    """
    def __init__(self,
                 name: str | None,
                 callback: Callable[[Player, dict], None],
                 emoji: str = None,
                 row: int | None = None,
                 style: ButtonStyle = discord.ButtonStyle.gray,
                 arguments: dict = None,
                 require_current_turn: bool = True):
        self.type = "button"
        self.limit = 25
        if not name:  # Empty string or None
            self.name = "​"  # Zero width space for no label
        else:
            self.name = name
        self.style = style
        self.callback = callback
        self.arguments = arguments
        self.row = row
        if emoji is None:
            self.emoji = None
        elif is_emoji(emoji):  # Default emoji
            self.emoji = emoji
        else:
            emoji_formatted = emoji.replace("<", "").replace(">", "").split(":")
            emoji_animated = emoji_formatted[0] == "a"
            if emoji_animated:
                emoji_name = emoji_formatted[1]
                emoji_id = int(emoji_formatted[2])
            else:
                emoji_name = emoji_formatted[0]
                emoji_id = int(emoji_formatted[1])
            self.emoji = discord.PartialEmoji(name=emoji_name, id=emoji_id, animated=emoji_animated)


        self.require_current_turn = require_current_turn
        if self.arguments is not None:
            self.parsed_arguments = ",".join([f'{key}={value}' for key, value in self.arguments.items()])
        else:
            self.parsed_arguments = ""

    def _view_transform(self, view: discord.ui.View, game_id):
        """
        Add the button to the view.
        :param view: View to add the button to.
        :param game_id: game ID for callback
        :return: Nothing (view object is passed as memory location)
        """

        # Note: c/ means current turn IS required, n/ means NO
        view.add_item(discord.ui.Button(style=discord.ButtonStyle.blurple,
                                        label=self.name,
                                        emoji=self.emoji,
                                        row=self.row,
                                        custom_id=f"{'c' if self.require_current_turn else 'n'}/{game_id}/"
                                                  f"{self.callback.__name__}/{self.parsed_arguments}"))