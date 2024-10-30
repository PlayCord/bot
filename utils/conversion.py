import discord

from utils.Database import formatted_elo


def convert_to_queued(some_players: list[discord.User], cached_elo, creator):
    return "\n".join([u.mention+f"{formatted_elo(cached_elo[u.id])} (Creator)" if u.id == creator.id else u.mention + f" {formatted_elo(cached_elo[u.id])}" for u in some_players])
