from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any

from api.MessageComponents import Container, Message
from configuration.constants import EMBED_COLOR, ERROR_COLOR, INFO_COLOR


class ResponseType(Enum):
    normal = 0
    info = 1
    error = 2


class Response:
    """
    Response: handler for command responses
    """

    def __init__(
            self,
            message: Message | None = None,
            content: str = None,
            style: ResponseType = None,
            ephemeral: bool = False,
            delete_after: int = None,
            *,
            record_replay: bool = False,
    ) -> None:
        """
        Create a new Response object.
[        :param content: plain text content of the response, outside of both the embed and view
        :param style: the style of the embed (normal, info, error)
        :param ephemeral: whether or not the embed is invisible to everyone but who called the callback
        :param delete_after: after how long to delete the message after it is sent
        :param record_replay: if True, this callback still counts as a game-affecting move for replay/DB when
            the handler returned a Response (normally only ``None`` means the move applied).
        """

        if style == ResponseType.normal:
            color = EMBED_COLOR
        elif style == ResponseType.info:
            color = INFO_COLOR
        elif style == ResponseType.error:
            color = ERROR_COLOR
        else:
            color = EMBED_COLOR  # Default color

        self.style = style or ResponseType.normal
        self.color = color
        self.content = content
        self.message = message
        self.ephemeral = ephemeral
        self.delete_after = delete_after
        self.record_replay = record_replay

    def _styled_message(self) -> Message | None:
        if self.message is None:
            return None
        if self.style == ResponseType.normal:
            return self.message
        return Message(Container(*self.message.children, accent_color=self.color), files=self.message.files)

    def generate_message(
            self,
            message_send_function: Callable[..., Awaitable[Any]],
            game_id: int = None,
            enable_embed_components: bool = True,
            enable_view_components: bool = True,
    ) -> tuple[Awaitable[Any], Callable[[Any], Awaitable[Any] | None]]:
        """
        Generate coroutines responsible for responding to the interaction
        :param message_send_function: the coroutine function that will send the Response
        :param game_id: Game ID the response is going to
        :return: An coroutine that will send the message,
         and a lambda function that takes a message and returns a coroutine to set the delete_after handler
        """

        async def dummy():
            return False

        payload = {"ephemeral": self.ephemeral}
        styled_message = self._styled_message()
        if styled_message is not None:
            payload.update(styled_message.to_send_kwargs(game_id, content=self.content))
        elif self.content is not None:
            payload["content"] = self.content
        else:
            return dummy(), lambda x: None

        return (message_send_function(**payload),
                lambda x: x.delete(delay=self.delete_after) if self.delete_after is not None else None)

    def send(
            self,
            message_send_function: Callable[..., Awaitable[Any]],
            game_id: int = None,
    ) -> tuple[Awaitable[Any], Callable[[Any], Awaitable[Any] | None]]:
        return self.generate_message(message_send_function, game_id)
