from api.Arguments import Integer
from api.Command import Command
from api.Game import Game
from api.MatchOptions import MatchOptionSpec
from api.MessageComponents import Container, MediaGallery, Message, TextDisplay, format_data_table_image
from api.Player import Player
from api.Response import Response


class NimGame(Game):
    summary = "Take stones from piles. Take the last stone to win (or lose in Misère)."
    move_command_group_description = "Commands for Nim"
    description = (
        "Classic Nim with three piles. On your turn, remove 1+ stones from one pile. "
        "Optional **Misère** rule (2 players): whoever takes the last stone loses."
    )
    name = "Nim"
    player_count = [2, 3, 4]
    trueskill_parameters = {"sigma": 1 / 4, "beta": 1 / 8, "tau": 1 / 150, "draw": 0}
    customizable_options = (
        MatchOptionSpec(
            key="win_condition",
            label="Win rule",
            kind="choices",
            default="normal",
            choices=(
                ("Normal — take last stone wins", "normal"),
                ("Misère — take last stone loses (2p)", "misere"),
            ),
        ),
    )
    moves = [
        Command(
            name="take",
            description="Take stones from a pile.",
            options=[
                Integer(argument_name="pile", description="Pile number (1-3)", min_value=1, max_value=3),
                Integer(argument_name="count", description="Stones to remove", min_value=1, max_value=20),
            ],
            callback="take",
        )
    ]
    author = "@quantumbagel"
    version = "1.0"
    author_link = "https://github.com/quantumbagel"
    source_link = "https://github.com/PlayCord/bot/blob/main/games/Nim.py"
    time = "3min"
    difficulty = "Easy"

    def __init__(self, players: list[Player], match_options: dict | None = None) -> None:
        self.players = players
        self.turn = 0
        self.piles = [3, 5, 7]
        self.finished = False
        self.winner: Player | None = None
        mo = match_options or {}
        raw_rule = mo.get("win_condition", "normal")
        self.misere = raw_rule == "misere" and len(self.players) == 2
        self.last_action = f"{self.current_turn().mention} starts."
        if self.misere:
            self.last_action += " **Misère:** last move loses."

    def state(self) -> Message:
        rule_note = " (Misère)" if self.misere else ""
        status = (
            f"🏁 Winner: {self.winner.mention}"
            if self.winner
            else f"➡️ Turn: {self.current_turn().mention}{rule_note}"
        )
        board = "\n".join([f"Pile {i + 1}: {'🪨' * n} ({n})" for i, n in enumerate(self.piles)])
        description = f"{status}\n\n{board}\n\n{self.last_action}"
        return Message(
            Container(
                TextDisplay(description),
                MediaGallery(format_data_table_image({p: {"Active": "✅" if p != self.winner else "🏆"} for p in self.players})),
            )
        )

    def current_turn(self) -> Player:
        return self.players[self.turn]

    def take(self, player: Player, pile: int, count: int):
        if self.finished:
            return Response(content="This game is already over.", ephemeral=True, delete_after=5)

        pile_index = pile - 1
        if pile_index < 0 or pile_index >= len(self.piles):
            return Response(content="Pile must be 1, 2, or 3.", ephemeral=True, delete_after=5)
        if count <= 0:
            return Response(content="Count must be at least 1.", ephemeral=True, delete_after=5)
        if self.piles[pile_index] < count:
            return Response(content="That pile doesn't have enough stones.", ephemeral=True, delete_after=5)

        self.piles[pile_index] -= count
        self.last_action = f"{player.mention} removed {count} from pile {pile}."

        if sum(self.piles) == 0:
            self.finished = True
            if self.misere:
                n = len(self.players)
                self.winner = self.players[(self.turn + 1) % n]
            else:
                self.winner = player
            return None

        self.turn = (self.turn + 1) % len(self.players)
        return None

    def outcome(self):
        if self.winner is not None:
            return self.winner
        return None

    def match_global_summary(self, outcome):
        if self.winner is None:
            return None
        suffix = " (misère)" if self.misere else ""
        return f"{self.winner.mention} won{suffix}"

    def match_summary(self, outcome):
        if self.winner is None:
            return None
        label = "Won (last stone)" if not self.misere else "Won (misère)"
        d = {self.winner.id: label}
        for p in self.players:
            if p.id != self.winner.id:
                d[p.id] = "Lost"
        return d
