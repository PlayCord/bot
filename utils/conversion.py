import random

import discord

from configuration.constants import LOGGING_ROOT
from utils.Player import Player


def convert_to_queued(some_players: list[Player], creator):
    return "\n".join([u.mention+f"{u.get_formatted_elo()} (Creator)" if u.id == creator.id else u.mention + f" {u.get_formatted_elo()}" for u in some_players])

def discord_users_to_player(game_type, users):

    pass

def textify(basis: dict[str,float], replacements: dict[str,str]):
    random_float = random.random()
    actually_picked_message = None
    if not len(basis.keys()):
        return f"{LOGGING_ROOT}.textify - CRITICAL - received empty input for basis"
    for possible_message in basis.keys():
        if random_float > basis[possible_message]:
            random_float -= basis[possible_message]
            continue
        else:
            actually_picked_message = possible_message
            break

    if actually_picked_message is None:
        actually_picked_message = possible_message

    for replacement in replacements.keys():
        actually_picked_message = actually_picked_message.replace("{"+replacement+"}", replacements[replacement])

    return actually_picked_message



