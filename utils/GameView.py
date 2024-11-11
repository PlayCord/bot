import asyncio
import importlib
import io
import random

import discord
from discord import Forbidden

from configuration import constants
from configuration.constants import *
from utils.CustomEmbed import CustomEmbed
from utils.Database import get_player
from utils.Player import Player
from utils.conversion import convert_to_queued, textify


class GameView:
    def __init__(self, game_type, status_message: discord.WebhookMessage, creator: discord.User,
                 player_obj: list[Player], rated: bool):
        self.status_message = status_message
        self.game_type = game_type
        self.creator = creator
        random.shuffle(player_obj)  # Randomize player order TODO: rework with introduction of team-based games
        self.players = player_obj
        self.rated = rated  # Is the game rated?
        self.thread = None
        self.game_message = None

        self.module = importlib.import_module(GAME_TYPES[game_type][0])
        self.game = getattr(self.module, GAME_TYPES[game_type][1])(self.players)

    async def thread_setup(self):
        rated_prefix = "Rated "
        if not self.rated:
            rated_prefix = ""

        game_thread = await self.status_message.channel.create_thread(name=f"{rated_prefix}{self.game_type} game (PlayCord)",
                                                  type=discord.ChannelType.private_thread, invitable=False)

        for player in self.players:
            await game_thread.add_user(player.user)
        getting_ready_embed = CustomEmbed(title="Almost done!", description="The game is about to start! This should only take a moment.")
        self.thread = game_thread
        self.game_message = await self.thread.send(embed=getting_ready_embed)

    async def move(self, arguments):
        print("inner", arguments)
        self.game.move(arguments)
        await self.display_game_state()
        print("updated")

    async def display_game_state(self):
        embed = CustomEmbed(title=f"Playing {self.game_type}",
                            description=textify(TEXTIFY_CURRENT_GAME_TURN,
                                    {"player": self.game.current_turn().mention}))
        picture_bytes = self.game.generate_game_picture()
        image = io.BytesIO()
        image.write(picture_bytes)
        image.seek(0)
        game_picture = discord.File(image, filename="image.png")
        embed.set_image(url="attachment://image.png")
        embed.set_footer(text="bagel.exe is not responding")  #
        embed.add_field(name="Players:", value=convert_to_queued(self.players, self.creator))
        await self.game_message.edit(embed=embed, attachments=[game_picture])





    async def run(self):
        while True:
            next_to_play_id = self.game.get_next_player_to_move()



class MatchmakingView:

    def __init__(self, creator: discord.User, game_type: str, message: discord.InteractionMessage, rated: bool):
        self.failed = None
        self.game_type = game_type
        self.creator = creator
        self.rated = rated
        self.module = importlib.import_module(GAME_TYPES[game_type][0])
        self.queued_players = [get_player(game_type, creator)]
        self.message = message
        if self.queued_players == [None]:
            fail_embed = CustomEmbed(title="Couldn't connect to database!", description="The bot failed to connect to the database."
                                                                                  " This is likely a temporary error, try again later!")
            self.failed = fail_embed
        self.has_followed_up = False
        self.game = getattr(self.module, GAME_TYPES[game_type][1])
        self.required_players = self.game.minimum_players
        self.maximum_players = self.game.maximum_players
        self.outcome = None


    async def callback_ready_game(self, ctx: discord.Interaction):
        await ctx.response.defer()
        if ctx.user.id in [p.id for p in self.queued_players]:
            await ctx.followup.send("You are already in the game!", ephemeral=True)
        else:
            new_player = get_player(self.game_type, ctx.user)
            if new_player is None:
                await ctx.followup.send("Couldn't connect to DB!", ephemeral=True)
                return False
            self.queued_players.append(new_player)
            await self.update_embed()
        return True

    async def callback_start_game(self, ctx: discord.Interaction):
        await ctx.response.defer()
        if ctx.user.id != self.creator.id:
            await ctx.followup.send("You can't start the game (not the creator).", ephemeral=True)
            return True
        embed = CustomEmbed(title=f"Loading game {self.game_type}...", description="This should only be a moment.")
        self.outcome = True
        await self.message.edit(embed=embed, view=None)
        await successful_matchmaking(self.game_type, self.message, self.creator,
                                     self.queued_players, self.rated)

    async def update_embed(self):
        embed = CustomEmbed(title="Waiting for players...", description=f"_There are currently {len(self.queued_players)} in the queue._\nThis game ({self.game_type}) /requires at least {self.required_players} players and at most {self.maximum_players} players.")
        embed.add_field(name="Players:", value=convert_to_queued(self.queued_players, self.creator), inline=False)
        view = discord.ui.View()
        join_button = discord.ui.Button(label="Join", style=discord.ButtonStyle.grey)
        leave_button = discord.ui.Button(label="Leave", style=discord.ButtonStyle.gray)
        start_enabled = self.maximum_players >= len(self.queued_players) >= self.required_players

        start_game_button = discord.ui.Button(label="Start", style=discord.ButtonStyle.blurple, disabled=not start_enabled)
        join_button.callback = self.callback_ready_game
        leave_button.callback = self.callback_leave_game
        start_game_button.callback = self.callback_start_game
        view.add_item(join_button)
        view.add_item(leave_button)
        view.add_item(start_game_button)
        # if not self.has_followed_up:
        #     self.message: discord.WebhookMessage | None = await self.followup.send(embed=embed, view=view)
        #     self.has_followed_up = True
        # else:
        #     await self.message.edit(embed=embed, view=view)
        await self.message.edit(embed=embed, view=view)


    async def callback_leave_game(self, ctx: discord.Interaction):
        await ctx.response.defer()
        if ctx.user.id not in [p.id for p in self.queued_players]:
            await ctx.followup.send("You aren't in the game!", ephemeral=True)
        else:
            for player in self.queued_players:
                if player.id == ctx.user.id:
                    self.queued_players.remove(player)
                    break
            if not len(self.queued_players):
                await ctx.followup.send("You were the last person in the lobby, so the game was cancelled!", ephemeral=True)
                await self.message.delete()
                self.outcome = False
                return
            if ctx.user.id == self.creator.id:
                self.creator = self.queued_players[0].user
            await self.update_embed()
        return True




async def successful_matchmaking(game_type, webhook_message, creator, player_objects, rated):
    join_thread_embed = CustomEmbed(title="Game started!", description="ya click button if u want to spectate")
    view = discord.ui.View()
    spectate_button = discord.ui.Button(label="� Spectate", style=discord.ButtonStyle.blurple)
    view.add_item(spectate_button)

    await webhook_message.edit(embed=join_thread_embed, view=view)

    game = GameView(game_type, webhook_message, creator, player_objects, rated)
    await game.thread_setup()
    constants.CURRENT_GAMES.update({game.status_message.channel.id: game}) # Register the game to the channel it's in
    constants.CURRENT_THREADS.update({game.thread.id: game.status_message.channel.id})

    await game.display_game_state()
