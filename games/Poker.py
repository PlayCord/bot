"""
Texas Hold'em Poker for PlayCord.

A simplified version of Texas Hold'em poker supporting 2-8 players.
Each player starts with chips and plays through betting rounds.
"""

import random
from itertools import combinations
from typing import Optional

from api.Command import Command
from api.Game import Game
from api.MessageComponents import Button, ButtonStyle, DataTable, Description
from api.Player import Player
from api.Response import Response


def _poker_ordinal(place: int) -> str:
    if place == 1:
        return "1st"
    if place == 2:
        return "2nd"
    if place == 3:
        return "3rd"
    return f"{place}th"


class Card:
    """Represents a playing card."""
    SUITS = ['♠', '♥', '♦', '♣']
    RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

    def __init__(self, rank: int, suit: int):
        """
        Create a card.
        :param rank: 0-12 (2 through A)
        :param suit: 0-3 (spades, hearts, diamonds, clubs)
        """
        self.rank = rank
        self.suit = suit

    @property
    def rank_str(self) -> str:
        return self.RANKS[self.rank]

    @property
    def suit_str(self) -> str:
        return self.SUITS[self.suit]

    def __str__(self) -> str:
        return f"{self.rank_str}{self.suit_str}"

    def __repr__(self) -> str:
        return str(self)


class Deck:
    """A standard 52-card deck."""

    def __init__(self):
        self.cards = [Card(r, s) for s in range(4) for r in range(13)]
        self.shuffle()

    def shuffle(self):
        random.shuffle(self.cards)
        # Pop order: last index first (see draw()). Chronological deal order for replay.
        self.deal_order = [str(c) for c in reversed(self.cards)]

    def draw(self) -> Card:
        return self.cards.pop()



def _straight_high_from_ranks(ranks: list[int]) -> int | None:
    """High card rank index of a 5-card straight; wheel (A-2-3-4-5) returns 3 (five-high)."""
    s = set(ranks)
    if len(s) < 5:
        return None
    if {12, 0, 1, 2, 3}.issubset(s):
        return 3
    ur = sorted(s, reverse=True)
    for i in range(len(ur) - 4):
        window = ur[i : i + 5]
        if window[0] - window[4] == 4 and all(
            window[j] - window[j + 1] == 1 for j in range(4)
        ):
            return window[0]
    return None


def _evaluate_five(cards: tuple[Card, ...]) -> tuple[int, ...]:
    """Return a comparison tuple; larger means a stronger 5-card hand."""
    ranks = [c.rank for c in cards]
    suits = [c.suit for c in cards]
    rank_counts: dict[int, int] = {}
    for r in ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1
    counts = sorted(rank_counts.items(), key=lambda x: (-x[1], -x[0]))
    is_flush = len(set(suits)) == 1
    st = _straight_high_from_ranks(ranks)
    if is_flush and st is not None:
        return (8, st)
    if counts[0][1] == 4:
        quad_rank = counts[0][0]
        kicker = max(r for r in ranks if r != quad_rank)
        return (7, quad_rank, kicker)
    if counts[0][1] == 3 and counts[1][1] == 2:
        return (6, counts[0][0], counts[1][0])
    if is_flush:
        return (5,) + tuple(sorted(ranks, reverse=True))
    if st is not None:
        return (4, st)
    if counts[0][1] == 3:
        trip = counts[0][0]
        kickers = sorted((r for r in ranks if r != trip), reverse=True)
        return (3, trip, kickers[0], kickers[1])
    pairs = sorted((r for r, c in rank_counts.items() if c == 2), reverse=True)
    if len(pairs) >= 2:
        hi, lo = pairs[0], pairs[1]
        kicker = max(r for r in ranks if r not in (hi, lo))
        return (2, hi, lo, kicker)
    if counts[0][1] == 2:
        pr = counts[0][0]
        kickers = sorted((r for r in ranks if r != pr), reverse=True)
        return (1, pr, kickers[0], kickers[1], kickers[2])
    return (0,) + tuple(sorted(ranks, reverse=True))


def _best_hand_strength(hole: list[Card], community: list[Card]) -> tuple[int, ...]:
    all_cards = hole + community
    if len(all_cards) < 5:
        return (0,)
    best: tuple[int, ...] | None = None
    for five in combinations(all_cards, 5):
        key = _evaluate_five(five)
        if best is None or key > best:
            best = key
    return best if best is not None else (0,)


class PokerGame(Game):
    """Texas Hold'em Poker implementation."""

    summary = "Play Texas Hold'em Poker!"
    move_command_group_description = "Commands for Poker"
    description = (
        "Texas Hold'em Poker - each player gets 2 hole cards, then 5 community cards "
        "are revealed. Make the best 5-card hand to win the pot!"
    )
    name = "Poker"
    player_count = [2, 3, 4, 5, 6, 7, 8]
    moves = [
        Command(name="peek", description="View your hole cards privately.",
                callback="peek", require_current_turn=False, is_game_affecting=False),
    ]
    author = "@quantumbagel"
    version = "1.0"
    author_link = "https://github.com/quantumbagel"
    source_link = "https://github.com/PlayCord/bot/blob/main/games/Poker.py"
    time = "15min"
    difficulty = "Hard"

    # Game settings
    STARTING_CHIPS = 1000
    SMALL_BLIND = 10
    BIG_BLIND = 20

    def __init__(self, players: list[Player]) -> None:
        self.players = players
        self.active_players = list(players)  # Players still in this hand
        self.turn = 0
        self.finished = False

        # Chip management
        self.chips = {p: self.STARTING_CHIPS for p in players}
        self.bets = {p: 0 for p in players}
        self.pot = 0
        self.current_bet = 0

        # Cards
        self.deck = Deck()
        self.hole_cards: dict[Player, list[Card]] = {p: [] for p in players}
        self.community_cards: list[Card] = []

        # Game state
        self.phase = "preflop"  # preflop, flop, turn, river, showdown
        self.folded: set[Player] = set()
        self.all_in: set[Player] = set()
        self.last_action = ""
        self.winner: Optional[Player] = None
        self.rankings: Optional[list[list[Player]]] = None

        # Deal hole cards
        self._deal_hole_cards()
        self._post_blinds()

    def on_replay_logger_attached(self) -> None:
        self.log_replay_event(
            {
                "type": "rng",
                "phase": "poker_deck_initial",
                "deal_order": getattr(self.deck, "deal_order", []),
            }
        )

    def _deal_hole_cards(self):
        """Deal 2 cards to each player."""
        for _ in range(2):
            for player in self.players:
                self.hole_cards[player].append(self.deck.draw())

    def _post_blinds(self):
        """Post small and big blinds."""
        if len(self.players) >= 2:
            # Small blind
            sb_player = self.players[0]
            sb_amount = min(self.SMALL_BLIND, self.chips[sb_player])
            self.chips[sb_player] -= sb_amount
            self.bets[sb_player] = sb_amount
            self.pot += sb_amount

            # Big blind
            bb_player = self.players[1]
            bb_amount = min(self.BIG_BLIND, self.chips[bb_player])
            self.chips[bb_player] -= bb_amount
            self.bets[bb_player] = bb_amount
            self.pot += bb_amount
            self.current_bet = bb_amount

            # Action starts after big blind
            self.turn = 2 % len(self.active_players)
            self.last_action = f"Blinds posted: {sb_player.mention} (SB: {sb_amount}), {bb_player.mention} (BB: {bb_amount})"

    def state(self):
        """Return current game state."""
        if self.finished:
            status = f"🏁 Game Over! Winner: {self.winner.mention}" if self.winner else "🏁 Game Over!"
        else:
            status = f"➡️ Turn: {self.current_turn().mention} | Phase: {self.phase.upper()}"

        # Community cards display
        if self.community_cards:
            community = " ".join(str(c) for c in self.community_cards)
        else:
            community = "No community cards yet"

        description = (
            f"{status}\n\n"
            f"**Community Cards:** {community}\n"
            f"**Pot:** {self.pot} chips\n"
            f"**Current Bet:** {self.current_bet}\n\n"
            f"{self.last_action}"
        )

        # Player status table
        table_data = {}
        for p in self.players:
            status_str = "Folded" if p in self.folded else ("All-In" if p in self.all_in else "Active")
            table_data[p] = {
                "Chips:": self.chips[p],
                "Bet:": self.bets[p],
                "Status:": status_str
            }

        components = [Description(description), DataTable(table_data)]

        # Add action buttons if game not finished
        if not self.finished and self.current_turn() not in self.folded:
            current = self.current_turn()
            can_check = self.bets[current] >= self.current_bet

            if can_check:
                components.append(Button(label="Check", callback=self.action_check,
                                         row=0, style=ButtonStyle.gray))
            else:
                call_amount = self.current_bet - self.bets[current]
                components.append(Button(label=f"Call ({call_amount})", callback=self.action_call,
                                         row=0, style=ButtonStyle.blurple))

            components.append(Button(label="Raise", callback=self.action_raise,
                                     row=0, style=ButtonStyle.green,
                                     arguments={"amount": self.BIG_BLIND}))
            components.append(Button(label="Fold", callback=self.action_fold,
                                     row=0, style=ButtonStyle.red))

        return components

    def current_turn(self) -> Player:
        """Return current player to act."""
        return self.active_players[self.turn % len(self.active_players)]

    def peek(self, player: Player):
        """Show player their hole cards privately."""
        cards = self.hole_cards.get(player, [])
        if cards:
            card_str = " ".join(str(c) for c in cards)
            return Response(content=f"Your hole cards: {card_str}", ephemeral=True)
        return Response(content="No cards dealt yet.", ephemeral=True)

    def action_check(self, player: Player):
        """Check (pass without betting)."""
        if self.bets[player] < self.current_bet:
            return Response(content="You can't check - you must call or raise.",
                            ephemeral=True, delete_after=5)

        self.last_action = f"{player.mention} checks."
        self._advance_turn()
        return None

    def action_call(self, player: Player):
        """Call the current bet."""
        call_amount = self.current_bet - self.bets[player]
        if call_amount <= 0:
            return Response(content="Nothing to call - try check instead.",
                            ephemeral=True, delete_after=5)

        actual_call = min(call_amount, self.chips[player])
        self.chips[player] -= actual_call
        self.bets[player] += actual_call
        self.pot += actual_call

        if self.chips[player] == 0:
            self.all_in.add(player)
            self.last_action = f"{player.mention} calls {actual_call} and is ALL-IN!"
        else:
            self.last_action = f"{player.mention} calls {actual_call}."

        self._advance_turn()
        return None

    def action_raise(self, player: Player, amount: int = None):
        """Raise the bet."""
        if amount is None:
            amount = self.BIG_BLIND

        call_amount = self.current_bet - self.bets[player]
        total_needed = call_amount + amount

        if total_needed > self.chips[player]:
            # All-in
            total_needed = self.chips[player]

        self.chips[player] -= total_needed
        self.bets[player] += total_needed
        self.pot += total_needed
        self.current_bet = self.bets[player]

        if self.chips[player] == 0:
            self.all_in.add(player)
            self.last_action = f"{player.mention} raises to {self.current_bet} and is ALL-IN!"
        else:
            self.last_action = f"{player.mention} raises to {self.current_bet}."

        self._advance_turn()
        return None

    def action_fold(self, player: Player):
        """Fold and forfeit the hand."""
        self.folded.add(player)
        if player in self.active_players:
            self.active_players.remove(player)

        self.last_action = f"{player.mention} folds."

        # Check if only one player remains
        remaining = [p for p in self.players if p not in self.folded]
        if len(remaining) == 1:
            self._end_hand([remaining[0]])
        else:
            self._advance_turn()

        return None

    def _advance_turn(self):
        """Move to next player or next phase."""
        # Check if betting round is complete
        active = [p for p in self.active_players if p not in self.folded and p not in self.all_in]

        if not active or self._betting_round_complete():
            self._next_phase()
        else:
            self.turn = (self.turn + 1) % len(self.active_players)
            while self.current_turn() in self.folded or self.current_turn() in self.all_in:
                self.turn = (self.turn + 1) % len(self.active_players)

    def _betting_round_complete(self) -> bool:
        """Check if all active players have matched the current bet."""
        for p in self.active_players:
            if p in self.folded or p in self.all_in:
                continue
            if self.bets[p] < self.current_bet:
                return False
        return True

    def _next_phase(self):
        """Advance to the next phase of the hand."""
        # Reset bets for new round
        for p in self.players:
            self.bets[p] = 0
        self.current_bet = 0
        self.turn = 0

        if self.phase == "preflop":
            self.phase = "flop"
            # Deal 3 community cards
            for _ in range(3):
                self.community_cards.append(self.deck.draw())
        elif self.phase == "flop":
            self.phase = "turn"
            self.community_cards.append(self.deck.draw())
        elif self.phase == "turn":
            self.phase = "river"
            self.community_cards.append(self.deck.draw())
        elif self.phase == "river":
            self.phase = "showdown"
            self._resolve_showdown()

    def _resolve_showdown(self):
        """Determine winner(s) at showdown from best 5-card hand (hole + board)."""
        remaining = [p for p in self.players if p not in self.folded]

        if len(remaining) == 1:
            self._end_hand([remaining[0]])
            return

        strengths: dict[Player, tuple[int, ...]] = {}
        for p in remaining:
            strengths[p] = _best_hand_strength(self.hole_cards[p], self.community_cards)
        best = max(strengths.values())
        winners = [p for p, k in strengths.items() if k == best]
        self.log_replay_event(
            {
                "type": "game_event",
                "phase": "poker_showdown",
                "strengths": {str(p.id): list(strengths[p]) for p in remaining},
                "winner_ids": [w.id for w in winners],
            }
        )
        self._end_hand(winners)

    def _end_hand(self, winners: list[Player]) -> None:
        """Award the pot; split evenly when multiple players tie the best hand."""
        if not winners:
            return
        pot = self.pot
        self.winner = winners[0]
        if len(winners) == 1:
            w = winners[0]
            self.chips[w] += pot
            self.last_action = f"🏆 {w.mention} wins {pot} chips!"
        else:
            n = len(winners)
            share, rem = divmod(pot, n)
            mentions = ", ".join(w.mention for w in winners)
            for i, w in enumerate(winners):
                self.chips[w] += share + (1 if i < rem else 0)
            self.last_action = f"🏆 Split pot ({pot} chips): {mentions}"
        self.pot = 0

        remaining_with_chips = [p for p in self.players if self.chips[p] > 0]
        if len(remaining_with_chips) == 1:
            self.finished = True
            self._build_rankings()

    def _build_rankings(self):
        """Build final rankings based on chip counts and elimination order."""
        # Sort by chips (descending), then by elimination order
        sorted_players = sorted(self.players, key=lambda p: self.chips[p], reverse=True)
        self.rankings = [[p] for p in sorted_players]

    def outcome(self):
        """Return game outcome."""
        if not self.finished:
            return None
        return self.rankings if self.rankings else [[self.winner]]

    def match_global_summary(self, outcome):
        if not self.finished or not isinstance(outcome, list):
            return None
        parts: list[str] = []
        for group in outcome:
            for p in group:
                chips = self.chips.get(p, 0)
                parts.append(f"{p.mention}: {chips}")
        if not parts:
            return None
        return "Final chips — " + " · ".join(parts)

    def match_summary(self, outcome):
        if not self.finished or not isinstance(outcome, list):
            return None
        result: dict[int, str] = {}
        for place_idx, group in enumerate(outcome):
            pos = place_idx + 1
            tie = len(group)
            for p in group:
                chips = self.chips.get(p, 0)
                if pos == 1:
                    text = (
                        f"Tied 1st ({chips} chips)" if tie > 1 else f"Won ({chips} chips)"
                    )
                else:
                    o = _poker_ordinal(pos)
                    text = (
                        f"Tied {o} ({chips} chips)" if tie > 1 else f"{o} place ({chips} chips)"
                    )
                result[p.id] = text
        return result or None
