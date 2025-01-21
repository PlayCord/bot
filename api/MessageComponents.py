import io
from typing import Callable
from emoji import is_emoji
import discord
from discord import ButtonStyle

from api.Player import Player


class MessageComponent:
    """
    MessageComponent: something used to represent game state
    """
    def __init__(self):
        """
        Create a new MessageComponent. As this is a non-usable class, it doesn't do anything.
        """
        pass

    def _embed_transform(self, embed: discord.Embed) -> None:
        """
        Transform the embed to add whatever parameter to it
        :param embed: the embed to transform
        :return: Nothing
        """
        pass

    def _view_transform(self, view: discord.ui.View, game_id: int) -> None:
        """
        Transform the view to add whatever parameter to it
        :param view: the view to transform
        :return: Nothing
        """
        pass


class Field(MessageComponent):
    """
    FieldType: something used to represent just a basic field
    """
    def __init__(self, name: str, value: str, inline: bool = False):
        """
        Create a new FieldType
        :param name: Name of the field
        :param value: value of the field
        :param inline: whether the field is inline or not.
        """
        super().__init__()

        # Instantiate the class
        self.name = name
        self.value = value
        self.inline = inline
        self.type = "field"  # API type
        self.limit = 25  # Discord api limitation

    def _embed_transform(self, embed: discord.Embed) -> None:
        """
        Transform the embed to add a Field to it
        :param embed: the embed to add a field to
        :return: Nothing
        """
        embed.add_field(name=self.name, value=self.value, inline=self.inline)


class DataTable(MessageComponent):
    """
    Creates a set of fields like this

    Name:      Param1:  ...
    Tyler       Thing   ...
    Julian      Thing2  ...
    """
    def __init__(self, data: dict) -> None:
        """
        Create a new data table
        :param data: data formatted like this:
        {Player: {"Column name": "Column Value"}, Player2: {"Column name": "Different Column Value"}, ...}

        Empty parameters are automatically filled in.
        """
        super().__init__()

        # Instantiate class data
        self.data = data
        self.type = "info_rows"
        self.limit = 1  # Only one dtaa table per embed

    def _embed_transform(self, embed: discord.Embed) -> None:
        """
        Transform the embed to add the fields that make up a data table
        :param embed: the embed to add the fields that make up a data table
        :return: Nothing
        """

        # Populate data in the format {data type: {person: value, person2, value}}
        column = {}
        for person in self.data:
            for data_type in self.data[person]:
                if data_type not in column:
                    column[data_type] = {person: str(self.data[person][data_type])}
                column[data_type].update({person: str(self.data[person][data_type])})

        # Check for empty data column and add empty values
        for data_type in column:
            for person in self.data:
                if person not in column[data_type]:
                    column[data_type].update({person: ""})

        # Add fields
        number_names = 0  # Number of Name: fields that have occurred
        for index in range((len(column)+(len(column)+1)//2)):
            if index % 3 == 0:  # Every third column should be a name column because discord
                embed.add_field(name="Name:", value="\n".join([str(p) for p in self.data.keys()]))
                number_names += 1
            else:  # Subtract number of names for formatting purposes
                embed.add_field(name=list(column.keys())[index - number_names], value="\n".join(column[list(column.keys())[index - number_names]].values()))



class Image(MessageComponent):
    """
    Image field in embed
    """
    def __init__(self, bytestring: bytes) -> None:
        """
        Represents the image as a byte string
        :param bytestring: bytes of the image
        """
        super().__init__()

        # Instantiate class variables
        self.limit = 1
        self.bytes = bytestring
        self.type = "image"

        # Engage in shenanigans to convert bytes to a file without saving it
        image = io.BytesIO()
        image.write(self.bytes)
        image.seek(0)
        self.game_picture = discord.File(image, filename="image.png")

    def _embed_transform(self, embed: discord.Embed) -> None:
        """
        Transform the embed to add the image
        :param embed: the embed to add the image to
        :return: nothing
        """
        # Add players and image to the embed
        embed.set_image(url="attachment://image.png")  # Set the attachment


class Footer(MessageComponent):
    """
    Footer field in embed
    """
    def __init__(self, text: str) -> None:
        """
        Create a new Footer. This just sets the footer
        :param text: the text of the footer to set
        """
        super().__init__()

        # Instantiate class variables
        self.type = "footer"
        self.text = text
        self.limit = 1

    def _embed_transform(self, embed: discord.Embed) -> None:
        """
        Transform the embed to add the footer
        :param embed: embed to add the footer to
        :return: nothing
        """
        embed.set_footer(text=self.text)


class Button(MessageComponent):
    """
    Represents a button for callbacks into the Game class
    """
    def __init__(self, name: str | None, callback: Callable[[Player, dict], None], emoji: str = None,
                 row: int | None = None, style: ButtonStyle = discord.ButtonStyle.gray, arguments: dict = None,
                 require_current_turn: bool = True) -> None:
        """
        Create a new Button. This represents a button for callbacks into the Game class
        :param name: label of button
        :param callback: callback function
        :param emoji: Emoji to use for the button
        :param row: which row the button is in (0-4, integer)
        :param style: coloring of button
        :param arguments: arguments to pass to the callback function
        :param require_current_turn: whether the button can only be used by the player whose turn it is
        """
        super().__init__()
        
        # Instantiate class options
        self.type = "button"
        self.limit = 25
        
        if not name:  # Empty string or None
            self.name = "​"  # Zero width space for no label
        else:
            self.name = name  # Just pass label as given
            
        
        self.style = style
        self.callback = callback
        self.arguments = arguments
        self.row = row
        
        if emoji is None:  # If no emoji, pass None
            self.emoji = None
        elif is_emoji(emoji):  # Default emoji, not custom emoji
            self.emoji = emoji
        else:  # Custom emoji
            
            # either [a, name, id] (animated), or [name, id] (static)
            emoji_formatted = emoji.replace("<", "").replace(">", "").split(":")
            
            emoji_animated = emoji_formatted[0] == "a"
            if emoji_animated:  # Animated
                emoji_name = emoji_formatted[1]
                emoji_id = int(emoji_formatted[2])
            else:  # static
                emoji_name = emoji_formatted[0]
                emoji_id = int(emoji_formatted[1])

            # Create PartialEmoji with data
            self.emoji = discord.PartialEmoji(name=emoji_name, id=emoji_id, animated=emoji_animated) 


        self.require_current_turn = require_current_turn
        if self.arguments is not None:  # create arguments like key=value,key2=value2
            self.parsed_arguments = ",".join([f'{key}={value}' for key, value in self.arguments.items()])
        else:
            self.parsed_arguments = ""  # no arguments, no problem

    def _view_transform(self, view: discord.ui.View, game_id: int) -> None:
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