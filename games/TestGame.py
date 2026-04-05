import logging
import random

from api.Command import Command
from api.Game import Game
from api.MessageComponents import Button, ButtonStyle, DataTable, Dropdown, Field, Footer, MessageComponent
from api.Player import Player
from api.Response import Response

log = logging.getLogger("playcord.testgame")


class TestGame(Game):
    summary: str = "A test game, to test the API features and make sure that things don't break."
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
        self.players = players
        self.turn = 0
        self.mode = "default"

    def return_callback(self, player) -> Response | None:
        return None

    def test_callback(self, player, values):
        return Response(content=f"Test callback: you put {values} in, cool")

    def state(self) -> list[MessageComponent]:
        data_table = {}
        for player in self.players:
            data_table[player] = {"RNG 1-10:": random.randint(1, 10), "Another column with int value": 2,
                                  "How about a float": 5, "What about a string": "test"}
        return [DataTable(data_table),
                Dropdown(data=[{"label": "1", "value": "test1", "description": "option 1"},
                               {"label": "2", "value": "test2", "description": "option 2"},
                               {"label": "3", "value": "test3", "description": "option 3"},
                               {"label": "4", "value": "test4", "description": "option 4"},
                               {"label": "5", "value": "test5", "description": "option 5"},
                               {"label": "6", "value": "test6", "description": "option 6"},
                               {"label": "7", "value": "test7", "description": "option 7"}],
                         callback=self.test_callback, placeholder="Input 1-6 options:", min_values=0, max_values=6),
                Field(name="Name (field example)", value="value (field example)"),
                Footer("Example Footer text"),
                Button(label="Example Button (green)", style=ButtonStyle.green, emoji="🗿",
                       disabled=True, callback=self.button_callback),
                ]

    def button_callback(self, player):
        log.debug("TestGame button callback called by %s", getattr(player, "name", player))

    def current_turn(self) -> Player:
        return self.players[self.turn]

    def outcome(self) -> Player | list[list[Player]] | str:
        return ""
