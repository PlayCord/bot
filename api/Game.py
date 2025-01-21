from api.Command import Command
from api.MessageComponents import MessageComponent
from api.Player import Player


class Game:
    """
    A generic, featureless Game object.
    """
    begin_command_description: str
    move_command_group_description: str
    description: str
    name: str
    players: int | list[int]
    moves = list[Command]
    author: str
    version: str
    author_link: str
    source_link: str
    time: str
    difficulty: str

    def __init__(self, players: list[Player]) -> None:
        """
        Create a new Game instance.
        :param players: a list of Players representing who will play the game.
        """
        pass

    def state(self) -> list[MessageComponent]:
        """
        Return the current state of the game using MessageComponents.
        :return: a list of MessageComponents representing the game state.
        """
        pass

    def current_turn(self) -> Player:
        """
        Return the current Player whose turn it is.
        It is highly recommended to make this function O(1) runtime
        due to the relative frequency it is called
        :return: the Player whose turn it is.
        """
        pass

    def outcome(self) -> Player | list[list[Player]] | str:
        """
        Return the outcome of the game state.

        :return: one Player who has won the game
        :return: a list of lists representing the outcome of the game. Each index is a place ([first, second, third]),
         and the inner list represents the people who got that place
        :return: string representing an error
        """
        pass

