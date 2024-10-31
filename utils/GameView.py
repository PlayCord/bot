import asyncio
import importlib
import random
from doctest import debug_src

import discord

from configuration.constants import *
from utils.CustomEmbed import CustomEmbed
from utils.Database import get_elo_for_player, formatted_elo
from utils.conversion import convert_to_queued


class GameView:
    def __init__(self, game_type, message: discord.WebhookMessage, creator: discord.User, player_obj: list[discord.User], cached_elo: list):
        self.message = message
        self.game_type = game_type
        self.creator = creator
        self.cached_elo = cached_elo
        random.shuffle(player_obj)
        self.players = player_obj
        self.turn = 0
        self.module = importlib.import_module(GAME_TYPES[game_type][0])
        self.game = getattr(self.module, GAME_TYPES[game_type][1])([player.id for player in self.players])


    async def display_game_state(self):
        embed = CustomEmbed(title=f"Playing {self.game_type}", description=f"It's {self.players[self.turn].mention}'s turn :)")
        game_picture = discord.File(self.game.generate_game_picture(), filename="image.png")
        embed.set_image(url="attachment://image.png")
        embed.set_footer(text="this is still a test.py. yes, really")
        embed.add_field(name="Players:", value=convert_to_queued(self.players, self.cached_elo, self.creator))
        await self.message.edit(embed=embed, attachments=[game_picture])





    async def run(self):
        while True:
            next_to_play_uuid = self.game.get_next_player_to_move()



class MatchmakingView:

    def __init__(self, creator: discord.User, game_type: str, followup: discord.Webhook):
        self.game_type = game_type
        self.creator = creator
        self.module = importlib.import_module(GAME_TYPES[game_type][0])
        self.queued_players_id = [creator.id]
        self.queued_players_obj = [creator]
        self.cached_elo = {creator.id: get_elo_for_player(self.game_type, creator.id)}
        self.followup = followup
        self.has_followed_up = False
        self.game = getattr(self.module, GAME_TYPES[game_type][1])
        self.required_players = self.game.minimum_players
        self.maximum_players = self.game.maximum_players
        self.outcome = None


    async def callback_ready_game(self, ctx: discord.Interaction):
        await ctx.response.defer()
        if ctx.user.id in self.queued_players_id:
            await ctx.followup.send("You are already in the game!", ephemeral=True)
        else:
            if ctx.user.id not in self.cached_elo.keys():
                self.cached_elo[ctx.user.id] = get_elo_for_player(self.game_type, ctx.user.id)
            self.queued_players_id.append(ctx.user.id)
            self.queued_players_obj.append(ctx.user)
            await self.update_embed()
        return True

    async def callback_start_game(self, ctx: discord.Interaction):
        await ctx.response.defer()
        if ctx.user.id != self.creator.id:
            await ctx.followup.send("You can't start the game (not the creator).", ephemeral=True)
            return True
        embed = CustomEmbed(title=f"Loading game {self.game_type}...", description="This should only be a moment.")
        self.outcome = True
        await self.followup.edit(embed=embed, view=None)
        await successful_matchmaking(self.game_type, self.followup, self.creator, self.queued_players_obj, self.cached_elo)

    async def update_embed(self):
        embed = CustomEmbed(title="Waiting for players...", description=f"_There are currently {len(self.queued_players_id)} in the queue._\nThis game ({self.game_type}) /requires at least {self.required_players} players and at most {self.maximum_players} players.")
        embed.add_field(name="Players:", value=convert_to_queued(self.queued_players_obj, self.cached_elo, self.creator), inline=False)
        view = discord.ui.View()
        join_button = discord.ui.Button(label="Join", style=discord.ButtonStyle.grey)
        leave_button = discord.ui.Button(label="Leave", style=discord.ButtonStyle.gray)
        start_enabled = self.maximum_players >= len(self.queued_players_id) >= self.required_players

        start_game_button = discord.ui.Button(label="Start", style=discord.ButtonStyle.blurple, disabled=not start_enabled)
        join_button.callback = self.callback_ready_game
        leave_button.callback = self.callback_leave_game
        start_game_button.callback = self.callback_start_game
        view.add_item(join_button)
        view.add_item(leave_button)
        view.add_item(start_game_button)
        if not self.has_followed_up:
            self.followup: discord.WebhookMessage = await self.followup.send(embed=embed, view=view)
            self.has_followed_up = True
        else:
            await self.followup.edit(embed=embed, view=view)


    async def callback_leave_game(self, ctx: discord.Interaction):
        await ctx.response.defer()
        if ctx.user.id not in self.queued_players_id:
            await ctx.followup.send("You aren't in the game!", ephemeral=True)
        else:
            where_is = self.queued_players_id.index(ctx.user.id)

            self.queued_players_id.remove(ctx.user.id)
            self.queued_players_obj.pop(where_is)

            if not len(self.queued_players_id):
                await ctx.followup.send("You were the last person in the lobby, so the game was cancelled!", ephemeral=True)
                await self.followup.delete()
                self.outcome = False
                return
            if ctx.user.id == self.creator.id:
                self.creator = self.queued_players_obj[0]

            await self.update_embed()
        return True

    async def create_initial_paint(self):
        join_button = discord.ui.Button(label="Join", style=discord.ButtonStyle.green)
        leave_button = discord.ui.Button(label="Leave", style=discord.ButtonStyle.red)
        join_button.callback = self.callback_ready_game
        leave_button.callback = self.callback_leave_game



async def successful_matchmaking(game_type, webhook_message, creator, player_objects, cached_elo):
    game = GameView(game_type, webhook_message, creator, player_objects, cached_elo)
    await game.display_game_state()
