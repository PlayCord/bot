from api.Command import Command
from api.MessageComponents import Dropdown, MessageComponent
from api.Player import Player
from api.Response import Response


class TestGame:
    begin_command_description: str = "A test game, to test the API features and make sure that things don't break."
    move_command_group_description: str = "A test game, to test the API features and make sure that things don't break."
    description: str = "A test game, to test the API features and make sure that things don't break."
    name: str = "API Test"
    players: int | list[int]
    moves: list[Command] = [Command(name="return", require_current_turn=False, callback="return_callback")]
    author: str
    version: str
    author_link: str
    source_link: str
    time: str
    difficulty: str = "Not a game"

    def __init__(self, players: list[Player]) -> None:
        """
        Create a new Game instance.
        :param players: a list of Players representing who will play the game.
        """
        self.players = players
        self.turn = 0
        self.mode = "default"

    def return_callback(self, player) -> Response:
        pass

    def test_callback(self, player, values):
        return Response(content=f"Test callback: you put {values} in, cool")

    def state(self) -> list[MessageComponent]:
        """
        Return the current state of the game using MessageComponents.
        :return: a list of MessageComponents representing the game state.
        """
        return [
            Dropdown(data=[{"label": "1", "value": "test1", "description": "option 1"},
                           {"label": "2", "value": "test2", "description": "option 2"},
                           {"label": "3", "value": "test3", "description": "option 3"},
                           {"label": "4", "value": "test4", "description": "option 4"},
                           {"label": "5", "value": "test5", "description": "option 5"},
                           {"label": "6", "value": "test6", "description": "option 6"},
                           {"label": "7", "value": "test7", "description": "option 7"}, ],
                     callback=self.test_callback, placeholder="Input 1-6 options:", min_values=0, max_values=6)]

    def current_turn(self) -> Player:
        """
        Return the current Player whose turn it is.
        It is highly recommended to make this function O(1) runtime
        due to the relative frequency it is called
        :return: the Player whose turn it is.
        """
        return self.players[self.turn]

    def outcome(self) -> Player | list[list[Player]] | str:
        """
        Return the outcome of the game state.

        :return: one Player who has won the game
        :return: a list of lists representing the outcome of the game. Each index is a place ([first, second, third]),
         and the inner list represents the people who got that place
        :return: string representing an error
        """
