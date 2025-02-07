from random import randint

from api.Arguments import Integer
from api.Command import Command
from api.Game import Game
from api.MessageComponents import *
from api.Response import Response


class LiarsDiceGame(Game):
    begin_command_description = "Wanna bluff?"
    move_command_group_description = "Commands for Liar's Dice"
    description = ("Liar's Dice is a game of deception, with nearly infinite possibilities."
                   " This version uses the \'reset\' variant.")
    name = "Liar's Dice"
    players = [2, 3, 4, 5, 6]
    moves = [Command(name="raise", description="Raise the bet.",
                     options=[
                         Integer(argument_name="dice_number", description="The number on the dice to call", min_value=1,
                                 max_value=6),
                         Integer(argument_name="number_of_dice", description="The number of dice to call", min_value=1,
                                 max_value=30)],
                     callback="callback_raise"),  # Max value = 6 (max players) * 5 (num dice per player)
             ]
    author = "@quantumbagel"
    version = "1.0"
    author_link = "https://github.com/quantumbagel"
    source_link = "https://github.com/PlayCord/bot/blob/main/games/LiarsDiceGame.py"
    time = "10min"
    difficulty = "Easy"

    def __init__(self, players):
        # Initial state information
        super().__init__(players)
        self.players = players
        self.hands = {p: [Die() for _ in range(5)] for p in players}
        self.eliminated = []
        self.current_bid = (0, 0)  # Dice #, number of dice
        self.turn = 0
        self.message = None
        self.round_state = None
        self.new_round_message()

    def new_round_message(self):
        self.message = f"A new round begins! {self.players[self.turn]}, make your move."
        self.round_state = "new_round"

    def raised_message(self):
        self.message = f"Player {self.players[self.turn - 1]} raises the bid to {self.current_bid}!"
        self.round_state = "after_first_raise"

    def end_round_message(self, who_called, who_was_called, did_succeed, total_count, bid_count, required_number):
        if did_succeed:
            succeed_verb = "and succeeded!"
            lost_die = who_was_called
        else:
            succeed_verb = "and failed!"
            lost_die = who_called
        self.message = (
            f"Player {who_called} called {who_was_called} {succeed_verb}. There were a total of {total_count} {required_number}, and the bid was {bid_count} {required_number}. {lost_die} lost a die. "
            f"They now have {len(self.hands[lost_die])} dice.")
        self.round_state = "end_round"

    def state(self):

        if self.round_state != "end_round":
            peek_button = Button(label="Peek", callback=self.callback_peek, row=0, style=ButtonStyle.gray,
                                 require_current_turn=False)
            call_button = Button(label="Call", callback=self.callback_call, row=0, style=ButtonStyle.red)
            view_components = [peek_button, call_button] if self.current_bid != (0, 0) else [peek_button]
            dice_data = {p: {"Dice:": len(self.hands[p])} for p in self.players}
            embed_components = [Description(self.message),
                                DataTable(dice_data)]

            return [*view_components, *embed_components]
        else:
            new_round_button = Button(label="New Round", callback=self.callback_new_round,
                                      row=0, style=ButtonStyle.green)
            dice_data = {p: {"Dice:": len(self.hands[p])} for p in self.players}
            embed_components = [Description(self.message),
                                DataTable(dice_data)]
            return [new_round_button, *embed_components]

    def current_turn(self):
        return self.players[self.turn]

    def callback_new_round(self, player):
        self.new_round_message()
        self.turn += 1
        if self.turn == len(self.players):
            self.turn = 0

    def callback_peek(self, player):
        return Response(content=stringify_hand(self.hands[player]), ephemeral=True)

    def callback_call(self, player):
        die_number_to_count = self.current_bid[0]
        total_counts_of_dice = 0
        for hand in self.hands.values():
            repr_hand = [1 for d in hand if d.number == die_number_to_count]
            total_counts_of_dice += len(repr_hand)

        if total_counts_of_dice >= self.current_bid[1]:  # If the bidder was right
            response = Response(content=f"Your call failed! (There were {total_counts_of_dice} of {die_number_to_count}"
                                        f" on a bid of {self.current_bid[1]})", ephemeral=True)
            self.hands[player].pop(0)  # Remove a die from the player who made the call
            self.end_round_message(player, self.players[self.turn - 1], False, total_counts_of_dice,
                                   self.current_bid[1], die_number_to_count)
            processed_player = player

        else:
            response = Response(
                content=f"Your call succeeded! (There were {total_counts_of_dice} of {die_number_to_count}"
                        f" on a bid of {self.current_bid[1]})", ephemeral=True)
            self.hands[self.players[self.turn - 1]].pop(0)
            self.end_round_message(player, self.players[self.turn - 1], True, total_counts_of_dice, self.current_bid[1],
                                   die_number_to_count)
            processed_player = self.players[self.turn - 1]

        if len(self.hands[processed_player]) == 0:  # This player is now out of the game
            self.players.remove(processed_player)
            self.eliminated.append(processed_player)  # Log their position in the eliminated list

        return response

    def callback_raise(self, player, dice_number, number_of_dice):
        total_dice_in_play = sum([len(h) for h in self.hands.values()])
        if number_of_dice > total_dice_in_play:  # Bid has too many dice
            return Response(
                content=f"Too many dice! (you bid {number_of_dice},"
                        f" total dice in play: {total_dice_in_play})",
                ephemeral=True, delete_after=3)

        current_bid_dice_number = self.current_bid[0]
        current_bid_number_of_dice = self.current_bid[1]
        if current_bid_dice_number < dice_number or \
                (current_bid_dice_number >= dice_number and current_bid_number_of_dice < number_of_dice):
            self.current_bid = (dice_number, number_of_dice)
            self.raised_message()
            self.turn += 1
            if self.turn == len(self.players):
                self.turn = 0
            return Response(content=f"Raised to bid {Die(number=dice_number)} # {number_of_dice}", ephemeral=True)
        else:
            return Response(
                content=f"Invalid bid!\nYour bid: {Die(number=dice_number)} # {number_of_dice},"
                        f"Current highest bid: {Die(number=current_bid_dice_number)} # {current_bid_number_of_dice}",
                ephemeral=True, delete_after=3)

    def outcome(self):
        pass


def stringify_hand(hand):
    return " ".join([str(die) for die in hand])


class Die:
    def __init__(self, number=None):
        if number is None:
            self.number = randint(1, 6)
        else:
            self.number = number

    def roll(self):
        self.number = randint(1, 6)

    def __str__(self):
        return str(self.number)
