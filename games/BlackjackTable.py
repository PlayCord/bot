import random

from api.Command import Command
from api.Game import Game
from api.MessageComponents import DataTable, Description
from api.Player import Player
from api.Response import Response


class BlackjackTableGame(Game):
    summary = "Multiplayer blackjack against the dealer."
    move_command_group_description = "Commands for Blackjack Table"
    description = "Players take turns hitting or standing; dealer plays after all stand or bust."
    name = "Blackjack Table"
    player_count = [2, 3, 4, 5, 6, 7]
    moves = [
        Command(name="hit", description="Draw one card.", callback="hit"),
        Command(name="stand", description="End your turn for this round.", callback="stand"),
        Command(name="peek", description="Show your hand privately.", callback="peek", require_current_turn=False,
                is_game_affecting=False),
    ]
    author = "@quantumbagel"
    version = "1.0"
    author_link = "https://github.com/quantumbagel"
    source_link = "https://github.com/PlayCord/bot/blob/main/games/BlackjackTable.py"
    time = "7min"
    difficulty = "Medium"

    def __init__(self, players: list[Player]) -> None:
        self.players = players
        self.turn = 0
        self.finished = False
        self.deck = self._make_shuffled_deck()
        self.hands: dict[Player, list[str]] = {p: [self._draw(), self._draw()] for p in players}
        self.stood: set[Player] = set()
        self.busted: set[Player] = set()
        self.dealer_hand: list[str] = [self._draw(), self._draw()]
        self.ranking_groups: list[list[Player]] | None = None
        self.last_action = f"{self.current_turn().mention} starts."

    def state(self):
        if self.finished:
            status = "🏁 Round complete."
            dealer_line = f"Dealer: {self._render_hand(self.dealer_hand)} ({self._hand_value(self.dealer_hand)})"
        else:
            status = f"➡️ Turn: {self.current_turn().mention}"
            dealer_line = f"Dealer: {self.dealer_hand[0]} ??"

        table = DataTable(
            {
                p: {
                    "Hand Value:": self._hand_value(self.hands[p]),
                    "Cards:": len(self.hands[p]),
                    "Status:": "Busted" if p in self.busted else ("Stood" if p in self.stood else "Playing"),
                }
                for p in self.players
            }
        )
        description = f"{status}\n{dealer_line}\n\n{self.last_action}"
        return [Description(description), table]

    def current_turn(self) -> Player:
        self._advance_turn_if_needed()
        return self.players[self.turn]

    def peek(self, player: Player):
        cards = self._render_hand(self.hands[player])
        return Response(content=f"Your hand: {cards} ({self._hand_value(self.hands[player])})", ephemeral=True)

    def hit(self, player: Player):
        if self.finished:
            return Response(content="Round is over.", ephemeral=True, delete_after=5)
        if player in self.stood:
            return Response(content="You already stood.", ephemeral=True, delete_after=5)
        if player in self.busted:
            return Response(content="You're busted and cannot hit.", ephemeral=True, delete_after=5)

        card = self._draw()
        self.hands[player].append(card)
        value = self._hand_value(self.hands[player])
        self.last_action = f"{player.mention} hits and draws {card}."

        if value > 21:
            self.busted.add(player)
            self.last_action += " Busted!"
            self._advance_turn()
        return None

    def stand(self, player: Player):
        if self.finished:
            return Response(content="Round is over.", ephemeral=True, delete_after=5)
        if player in self.stood:
            return Response(content="You already stood.", ephemeral=True, delete_after=5)
        if player in self.busted:
            return Response(content="You're busted already.", ephemeral=True, delete_after=5)

        self.stood.add(player)
        self.last_action = f"{player.mention} stands."
        self._advance_turn()
        return None

    def outcome(self):
        if self.ranking_groups is not None:
            return self.ranking_groups

        if self.finished:
            return None

        active = [p for p in self.players if p not in self.stood and p not in self.busted]
        if active:
            return None

        self._dealer_play()
        dealer_value = self._hand_value(self.dealer_hand)
        scored = []
        for player in self.players:
            value = self._hand_value(self.hands[player])
            if player in self.busted:
                score = -1
            elif dealer_value > 21:
                score = value
            elif value > dealer_value:
                score = value
            elif value == dealer_value:
                score = 0
            else:
                score = -1
            scored.append((player, score, value))

        scored.sort(key=lambda x: (x[1], x[2]), reverse=True)
        groups: list[list[Player]] = []
        for player, score, value in scored:
            if not groups:
                groups.append([player])
            else:
                prev = groups[-1][0]
                prev_tuple = next(item for item in scored if item[0] == prev)
                if (score, value) == (prev_tuple[1], prev_tuple[2]):
                    groups[-1].append(player)
                else:
                    groups.append([player])

        self.finished = True
        self.ranking_groups = groups
        self.last_action = f"Dealer reveals {self._render_hand(self.dealer_hand)} ({dealer_value})."
        return groups

    def match_global_summary(self, outcome):
        if not self.finished or not isinstance(outcome, list):
            return None
        dv = self._hand_value(self.dealer_hand)
        bits = [f"{p.mention} {self._hand_value(self.hands[p])}" for p in self.players]
        return f"Dealer {dv} — " + " · ".join(bits)

    def match_summary(self, outcome):
        if not self.finished or not isinstance(outcome, list):
            return None
        result: dict[int, str] = {}

        def ord_s(place: int) -> str:
            return {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th", 7: "7th"}.get(place, f"{place}th")

        for place_idx, group in enumerate(outcome):
            pos = place_idx + 1
            tie = len(group)
            for p in group:
                hv = self._hand_value(self.hands[p])
                label = "bust" if p in self.busted else str(hv)
                if pos == 1:
                    text = f"Tied 1st ({label})" if tie > 1 else f"Won ({label})"
                else:
                    o = ord_s(pos)
                    text = f"Tied {o} ({label})" if tie > 1 else f"{o} place ({label})"
                result[p.id] = text
        return result

    def _advance_turn(self):
        self.turn = (self.turn + 1) % len(self.players)
        self._advance_turn_if_needed()

    def _advance_turn_if_needed(self):
        for _ in range(len(self.players)):
            p = self.players[self.turn]
            if p not in self.stood and p not in self.busted:
                return
            self.turn = (self.turn + 1) % len(self.players)

    def _dealer_play(self):
        while self._hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self._draw())

    def _draw(self) -> str:
        if not self.deck:
            self.deck = self._make_shuffled_deck()
        return self.deck.pop()

    def _make_shuffled_deck(self) -> list[str]:
        values = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
        suits = ["♠", "♥", "♦", "♣"]
        deck = [f"{v}{s}" for v in values for s in suits]
        random.shuffle(deck)
        # _draw uses pop() → chronological deal order is reversed list
        self.log_replay_event(
            {"type": "rng", "phase": "blackjack_shuffle", "deal_order": list(reversed(deck))}
        )
        return deck

    def _hand_value(self, hand: list[str]) -> int:
        value = 0
        aces = 0
        for card in hand:
            rank = card[:-1]
            if rank == "A":
                aces += 1
                value += 11
            elif rank in {"K", "Q", "J"}:
                value += 10
            else:
                value += int(rank)

        while value > 21 and aces > 0:
            value -= 10
            aces -= 1
        return value

    def _render_hand(self, hand: list[str]) -> str:
        return " ".join(hand)
