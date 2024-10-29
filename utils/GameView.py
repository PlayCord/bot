import asyncio
import importlib

import discord

from configuration.constants import *


class GameView:
    def __init__(self, game_type, message: discord.Webhook, creator: discord.User):
        self.message = message
        self.game_type = game_type
        self.creator = creator
        self.module = importlib.import_module(GAME_TYPES[game_type][0])
        self.game = getattr(self.module, GAME_TYPES[game_type][1])
        self.ready = [self.creator.id]

    async def ready_game(self, ctx: discord.Interaction):
        await ctx.message.edit(content="hi ig")


    async def display_ready_view(self):
        embed = discord.Embed(title="Waiting for players...", description=f"{len(self.ready)}/{min(self.game.game_state.players)}\n{self.game.description}")
        view = discord.ui.View()

        ready_button = discord.ui.Button(label="Ready", style=discord.ButtonStyle.green)
        leave_button = discord.ui.Button(label="Leave", style=discord.ButtonStyle.red)
        ready_button.callback = self.ready_game
        view.add_item(ready_button)
        await self.message.send(embed=embed, view=view)

    async def run(self):
        while True:
            next_to_play_uuid = self.game.get_next_player_to_move()


class MatchmakingView:

    def __init__(self, creator: discord.User, game_type: str, followup: discord.Webhook):
        self.game_type = game_type
        self.creator = creator
        self.module = importlib.import_module(GAME_TYPES[game_type][0])
        self.queued_players = [creator.id]
        self.followup = followup
        self.has_followed_up = False
        self.game = getattr(self.module, GAME_TYPES[game_type][1])

    async def callback_ready_game(self, ctx: discord.Interaction):
        await ctx.response.defer()
        if ctx.user.id in self.queued_players:
            await ctx.followup.send("You are already in the game!", ephemeral=True)
        else:
            self.queued_players.append(ctx.user.id)
            await self.generate_embed()
        return True


    async def generate_embed(self):
        embed = discord.Embed(title="Waiting for players...", description=f"_There are currently {len(self.queued_players)} in the queue._")
        view = discord.ui.View()
        join_button = discord.ui.Button(label="Join", style=discord.ButtonStyle.green)
        leave_button = discord.ui.Button(label="Leave", style=discord.ButtonStyle.red)

        join_button.callback = self.callback_ready_game
        leave_button.callback = self.callback_leave_game
        view.add_item(join_button)
        view.add_item(leave_button)
        if not self.has_followed_up:
            self.followup = await self.followup.send(embed=embed, view=view)
            self.has_followed_up = True
        else:
            await self.followup.edit(embed=embed, view=view)


    async def callback_leave_game(self, ctx: discord.Interaction):
        await ctx.response.defer()
        if ctx.user.id not in self.queued_players:
            await ctx.followup.send("You aren't in the game!", ephemeral=True)
        else:
            self.queued_players.remove(ctx.user.id)
            await self.generate_embed()
        return True

    async def create_initial_paint(self):
        join_button = discord.ui.Button(label="Join", style=discord.ButtonStyle.green)
        leave_button = discord.ui.Button(label="Leave", style=discord.ButtonStyle.red)
        join_button.callback = self.callback_ready_game
        leave_button.callback = self.callback_leave_game

