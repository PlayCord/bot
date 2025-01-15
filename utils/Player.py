import builtins
import decimal

import discord
from trueskill import TrueSkill

from configuration.constants import SIGMA_RELATIVE_UNCERTAINTY_THRESHOLD


class Player:
    def __init__(self, mu, sigma, user: discord.User | discord.Object, ranking = None):
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
        self.ranking = ranking

    @property
    def mention(self):
        return f"<@{self.id}>"  # Don't use the potential self.user.mention because it could be an Object

    def move(self, new_player_data: dict):
        self.moves_made += 1
        self.player_data.update(new_player_data)

    def get_formatted_elo(self):
        if self.ranking is None:
            ranking_addend = ""
        else:
            ranking_addend = f" (#{self.ranking})"
        if self.sigma > SIGMA_RELATIVE_UNCERTAINTY_THRESHOLD * self.mu:  # TODO: confirm
            return str(int(self.mu)) + "?" + ranking_addend
        else:
            return str(int(self.mu)) + ranking_addend


    def __eq__(self, other):
        if other is None:
            return False
        return self.id == other.id and self.mu == other.mu and self.sigma == other.sigma


    def __hash__(self):
        return hash(repr(self))

    def __str__(self):
        return self.mention

    def __repr__(self):
        return f"Player(id={self.id}, mu={self.mu}, sigma={self.sigma})"