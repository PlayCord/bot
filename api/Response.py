import collections
from enum import Enum
from types import coroutine

import discord

from api.MessageComponents import MessageComponent
from configuration.constants import EMBED_COLOR, ERROR_COLOR, INFO_COLOR
from utils.embeds import CustomEmbed


class ResponseType(Enum):
    normal = 0
    info = 1
    error = 2


class Response:
    """
    Response: handler for command responses
    """

    def __init__(self, components: list[MessageComponent] = None, content: str = None, style: ResponseType = None,
                 ephemeral: bool = False, delete_after: int = None) -> None:
        """
        Create a new Response object.
        :param components: list of MessageComponent objects to put in the response
        :param content: plain text content of the response, outside of both the embed and view
        :param style: the style of the embed (normal, info, error)
        :param ephemeral: whether or not the embed is invisible to everyone but who called the callback
        :param delete_after: after how long to delete the message after it is sent
        """

        # Get embed color
        if style == ResponseType.normal:
            color = EMBED_COLOR
        elif style == ResponseType.info:
            color = INFO_COLOR
        elif style == ResponseType.error:
            color = ERROR_COLOR
        else:
            color = EMBED_COLOR  # Default color

        # Set up class instance variables
        self.color = color
        self.content = content
        self.components = components
        if not self.components:  # if None, set empty list
            self.components = []
        self.ephemeral = ephemeral
        self.delete_after = delete_after

    def generate_message(self, message_send_function: coroutine, game_id: int = None,
                         enable_embed_components: bool = True, enable_view_components: bool = True) \
            -> tuple[coroutine, collections.abc.Callable[..., coroutine]]:
        """
        Generate coroutines responsible for responding to the interaction
        :param message_send_function: the coroutine function that will send the Response
        :param game_id: Game ID the response is going to
        :param enable_embed_components: whether the message should use the embed-compatible components
        :param enable_view_components:whether the message should use the view-compatible components
        :return: An coroutine that will send the message,
         and a lambda function that takes a message and returns a coroutine to set the delete_after handler
        """
        # Starting embed and view
        embed = CustomEmbed(color=self.color)
        view = discord.ui.View()
        should_embed_be_sent = False
        should_view_be_sent = False
        for component in self.components:
            # Perform both embed and view transformations
            if hasattr(component, '_embed_transform') and enable_embed_components:
                should_embed_be_sent = True
                component._embed_transform(embed)
            if hasattr(component, '_view_transform') and enable_view_components:
                should_view_be_sent = True
                component._view_transform(view, game_id)

        # Return only the components that are enabled. This way we can filter out either View or Embed components
        message_data = {"content": self.content, "ephemeral": self.ephemeral}

        # Require both that there is at least one component and that the component type is enabled
        if enable_embed_components and should_embed_be_sent:
            message_data.update({"embed": embed})
        if enable_view_components and should_view_be_sent:
            message_data.update({"view": view})

        # Return the coroutine to send the message and a lambda to add the delete after set by the Game object
        return (message_send_function(**message_data),
                lambda x: x.delete(delay=self.delete_after))
