import builtins
import decimal

import discord
from trueskill import TrueSkill

from configuration.constants import SIGMA_RELATIVE_UNCERTAINTY_THRESHOLD


class Player:
    def __init__(self, mu, sigma, user: discord.User | discord.Object):
        self.user = user
        self.mu = mu
        self.sigma = sigma
        if isinstance(user, discord.User):
            self.name = user.name
        else:
            self.name = None
        self.id = user.id
        self.player_data = {}
        self.moves_made = 0

    @property
    def mention(self):
        return f"<@{self.id}>"  # Don't use the potential self.user.mention because it could be a Object

    def move(self, new_player_data: dict):
        self.moves_made += 1
        self.player_data.update(new_player_data)

    def get_formatted_elo(self):
        if self.sigma > SIGMA_RELATIVE_UNCERTAINTY_THRESHOLD * self.mu:  # TODO: confirm
            return str(int(self.mu)) + "?"
        else:
            return str(int(self.mu))

    def __eq__(self, other):
        if other is None:
            return False
        return self.id == other.id and self.mu == other.mu and self.sigma == other.sigma


    def __hash__(self):
        return hash(repr(self))
