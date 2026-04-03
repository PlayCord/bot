from abc import ABC, abstractmethod
from enum import Enum

from api.Bot import Bot
from api.Command import Command
from api.MessageComponents import MessageComponent
from api.Player import Player


def _normalize_player_count_spec(value: object) -> int | list[int] | None:
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return None


def resolve_player_count(game: object) -> int | list[int] | None:
    """
    Return allowed player counts for a game class/object.
    """
    resolver = getattr(game, "required_player_count", None)
    if callable(resolver):
        return _normalize_player_count_spec(resolver())

    return _normalize_player_count_spec(
        getattr(game, "player_count", None)
    )


class PlayerOrder(Enum):
    """Enum for specifying player order behavior."""
    RANDOM = "random"  # Randomize player order (default)
    PRESERVE = "preserve"  # Keep the order players joined
    CREATOR_FIRST = "creator_first"  # Creator always goes first, rest randomized
    REVERSE = "reverse"  # Reverse the join order


class Game(ABC):
    """
    A generic, featureless Game object.

    Games should inherit from this class and implement the required methods.

    Class Attributes:
        summary (str): Description shown in /play command
        move_command_group_description (str): Description for move commands group
        description (str): Full description of the game
        name (str): Human-readable name of the game
        player_count (int | list[int]): Number of players allowed
        moves (list[Command]): List of move commands
        bots (dict[str, Bot]): Available bot difficulties for this game
        author (str): Game author
        version (str): Game version
        author_link (str): Link to author's page
        source_link (str): Link to source code
        time (str): Estimated game duration
        difficulty (str): Game difficulty level
        player_order (PlayerOrder): How to order players (default: RANDOM)
    """
    summary: str
    move_command_group_description: str
    description: str
    name: str
    player_count: int | list[int]
    moves: list[Command] = []
    bots: dict[str, Bot] = {}
    author: str
    version: str
    author_link: str
    source_link: str
    time: str
    difficulty: str
    player_order: PlayerOrder = PlayerOrder.RANDOM
    game_schema_version: int = 1

    @abstractmethod
    def __init__(self, players: list[Player]) -> None:
        """
        Create a new Game instance.
        :param players: a list of Players representing who will play the game.
        """
        raise NotImplementedError

    @abstractmethod
    def state(self) -> list[MessageComponent]:
        """
        Return the current state of the game using MessageComponents.
        :return: a list of MessageComponents representing the game state.
        """
        raise NotImplementedError

    @abstractmethod
    def current_turn(self) -> Player:
        """
        Return the current Player whose turn it is.
        It is highly recommended to make this function O(1) runtime
        due to the relative frequency it is called
        :return: the Player whose turn it is.
        """
        raise NotImplementedError

    @abstractmethod
    def outcome(self) -> Player | list[list[Player]] | str:
        """
        Return the outcome of the game state.

        :return: one Player who has won the game
        :return: a list of lists representing the outcome of the game. Each index is a place ([first, second, third]),
         and the inner list represents the people who got that place
        :return: string representing an error
        """
        raise NotImplementedError

    @classmethod
    def supports_bots(cls) -> bool:
        """Return True when the game defines at least one bot difficulty."""
        return bool(getattr(cls, "bots", {}))

    @classmethod
    def required_player_count(cls) -> int | list[int] | None:
        """Return allowed player counts, including legacy metadata fallback."""
        return _normalize_player_count_spec(
            getattr(cls, "player_count", None)
        )
