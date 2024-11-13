import builtins

import discord

from configuration.constants import SIGMA_RELATIVE_UNCERTAINTY_THRESHOLD


class Player:
    def __init__(self, mu, sigma, user: discord.User):
        self.user = user
        self.mu = mu
        self.sigma = sigma
        self.name = user.name
        self.id = user.id
        self.player_data = {}
        self.moves_made = 0
        self.eliminated = False

    @property
    def mention(self):
        return self.user.mention

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
        return self.id == other.id and self.name == other.name and self.mu == other.mu and self.sigma == other.sigma


