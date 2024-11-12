import random
from configuration.constants import LOGGING_ROOT
from utils.Player import Player


def convert_to_queued(players: list[Player], creator) -> str:
    """
    Convert a list of players into a string representing the list of players

    ex:
    @Player1 25? (Creator)
    @Player2 50
    @Player3 100000?

    TODO: add additional functionality (like nonrated games)

    :param players: the players to create a list from
    :param creator: the Player object representing the player who created the lobby
    :return: the concatenated string
    """
    return "\n".join([u.mention+f"{u.get_formatted_elo()} (Creator)" if u.id == creator.id
                      else u.mention + f" {u.get_formatted_elo()}" for u in players])



def textify(basis: dict[str,float], replacements: dict[str,str]) -> str:
    """
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
