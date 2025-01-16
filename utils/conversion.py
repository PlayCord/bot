import random

import discord
from discord import User

from configuration.constants import LOGGING_ROOT
from utils.Player import Player


def column_names(players: list[Player] | set[Player]) -> str:
    """
    Convert a list of players into a string representing the list of players

    @player
    @player2
    """
    return "\n".join([u.mention for u in players])

def column_elo(players: list[Player] | set[Player]) -> str:
    """
    Convert a list of players into a string representing the list of players

    238
    237?
    """
    return "\n".join([u.get_formatted_elo() for u in players])

def column_creator(players: list[Player] | set[Player], creator: Player | User) -> str:
    """
    Convert a list of players into a string representing the list of players's creator status

    Creator
    <blank>
    """
    return "\n".join(["Creator" if u.id == creator.id else "" for u in players])


def column_turn(players: list[Player] | set[Player], turn: Player | User) -> str:
    """
    Convert a list of players into a string representing the list of players

    Creator
    <blank>
    """
    return "\n".join(["✅" if u.id == turn.id else "" for u in players])



def textify(basis: dict[str,float], replacements: dict[str,str]) -> str:
    """de
    Randomly pick a message and fill variables
    :param basis: A list of messages
    :param replacements: A list of things to replace
    (ex: "The {person} rolls..." with argument {"person": "John Wick"}
    -> "The John Wick rolls..."
    :return: the randomly generated string
    """
    random_float = random.random()  # Pick a number between 0 and 1
    actually_picked_message = None

    if not len(basis.keys()):  # Make sure there is
        return f"{LOGGING_ROOT}.textify - CRITICAL - received empty input for basis"

    # Here's how this code block works
    # we have probabilities:
    # 0.3 Message 1 (0 <= random_float <= 0.3)
    # 0.3 Message 2 (0.3 < random_float <= 0.6)
    # 0.2 Message 3 (0.6 < random_float <= 0.8)
    # 0.2 Message 4 (0.8 < random_float <= 1.0)
    for possible_message in basis.keys():
        if random_float > basis[possible_message]:  # keep going
            random_float -= basis[possible_message]
            continue
        else:  # random_float falls into this probability block
            actually_picked_message = possible_message
            break

    if actually_picked_message is None:
        # This is not an error because possible_message must be defined because of the empty check
        actually_picked_message = possible_message

    # Replace the strings with their replacements (great english)
    for replacement in replacements.keys():
        actually_picked_message = actually_picked_message.replace("{"+replacement+"}", replacements[replacement])

    return actually_picked_message

def player_representative(possible_players):
    if type(possible_players) == int:
        return str(possible_players)
    nums = sorted(set(possible_players))

    result = []
    start = nums[0]
    for i in range(1, len(nums) + 1):
        # Check if the current number is not consecutive
        if i == len(nums) or nums[i] != nums[i - 1] + 1:
            # If there's a range (start != nums[i-1]), add range, else just a single number
            if start == nums[i - 1]:
                result.append(str(start))
            else:
                result.append(f"{start}-{nums[i - 1]}")
            if i < len(nums):
                start = nums[i]

    return ", ".join(result)

def player_verification_function(possible_players):
    if type(possible_players) == int:
        return lambda x: x == possible_players
    else:
        return lambda x: x in set(possible_players)


def contextify(ctx: discord.Interaction):
    return f"guild_id={ctx.guild.id} guild_name={ctx.guild.name!r} user_id={ctx.user.id}, user_name={ctx.user.name}, is_bot={ctx.user.bot}, data={ctx.data}, type={ctx.type!r}"