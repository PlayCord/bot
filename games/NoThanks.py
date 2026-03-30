import random

from api.Command import Command
from api.Game import Game
from api.MessageComponents import DataTable, Description
from api.Player import Player
from api.Response import Response


class NoThanksGame(Game):
    begin_command_description = "Take cards or pass with chips in No Thanks!"
    move_command_group_description = "Commands for No Thanks!"
    description = "On your turn, either take the face-up card with chips or spend one chip to pass."
    name = "No Thanks!"
    players = [3, 4, 5, 6, 7]
    moves = [
        Command(name="take", description="Take the current card.", callback="take"),
        Command(name="pass", description="Pay one chip to pass.", callback="pass_turn"),
    ]
    author = "@quantumbagel"
    version = "1.0"
    author_link = "https://github.com/quantumbagel"
    source_link = "https://github.com/PlayCord/bot/blob/main/games/NoThanks.py"
    time = "8min"
    difficulty = "Medium"

    def __init__(self, players: list[Player]) -> None:
        self.players = players
        self.turn = 0
        self.finished = False

        deck = list(range(3, 36))
        random.shuffle(deck)
        removed = set(deck[:9])
        self.deck = [card for card in deck[9:] if card not in removed]

        self.current_card = self.deck.pop(0)
        self.pot = 0
        self.chips = {p: 11 for p in players}
        self.cards = {p: [] for p in players}
        self.last_action = f"{self.current_turn().mention} starts. Current card: {self.current_card}."

    def state(self):
        status = "🏁 Game over." if self.finished else f"➡️ Turn: {self.current_turn().mention}"
        table = DataTable(
            {p: {"Chips:": self.chips[p], "Cards:": len(self.cards[p]), "Score:": self._score_player(p)} for p in
             self.players}
        )
        description = (
            f"{status}\nCurrent card: **{self.current_card}**\nChips on card: **{self.pot}**\n\n{self.last_action}"
        )
        return [Description(description), table]

    def current_turn(self) -> Player:
        return self.players[self.turn]

    def pass_turn(self, player: Player):
        if self.finished:
            return Response(content="This game is already over.", ephemeral=True, delete_after=5)
        if self.chips[player] <= 0:
            return Response(content="You have no chips left, so you must take.", ephemeral=True, delete_after=5)

        self.chips[player] -= 1
        self.pot += 1
        self.turn = (self.turn + 1) % len(self.players)
        self.last_action = f"{player.mention} passed and paid 1 chip."
        return None

    def take(self, player: Player):
        if self.finished:
            return Response(content="This game is already over.", ephemeral=True, delete_after=5)

        self.cards[player].append(self.current_card)
        self.cards[player].sort()
        self.chips[player] += self.pot
        self.last_action = f"{player.mention} took {self.current_card} and {self.pot} chip(s)."
        self.pot = 0

        if not self.deck:
            self.finished = True
            return None

        self.current_card = self.deck.pop(0)
        return None

    def outcome(self):
        if not self.finished:
            return None

        scored = [(p, self._score_player(p)) for p in self.players]
        scored.sort(key=lambda item: item[1])

        groups: list[list[Player]] = []
        for player, score in scored:
            if not groups:
                groups.append([player])
                continue
            prev_score = self._score_player(groups[-1][0])
            if score == prev_score:
                groups[-1].append(player)
            else:
                groups.append([player])
        return groups

    def _score_player(self, player: Player) -> int:
        cards = sorted(self.cards[player])
        if not cards:
            card_score = 0
        else:
            card_score = cards[0]
            for i in range(1, len(cards)):
                if cards[i] != cards[i - 1] + 1:
                    card_score += cards[i]
        return card_score - self.chips[player]
