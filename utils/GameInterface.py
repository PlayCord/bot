import importlib
import io
import random
import typing

from configuration import constants
from configuration.constants import *
from utils.CustomEmbed import CustomEmbed
from utils.Database import get_player
from utils.Player import Player
from utils.conversion import convert_to_queued, textify


class GameInterface:
    """
    A class that handles the interface between the game and discord

    Discord <--> Bot <--> GameInterface <--> Game
    """
    def __init__(self, game_type: str, status_message: discord.WebhookMessage, creator: discord.User,
                 players: list[Player], rated: bool) -> None:
        """
        Create the GameInterface
        :param game_type: The game type as defined in constants.py
        :param status_message: The message already created by the bot outside the not-yet-existent thread
        :param creator: the User (discord) who created the lobby TODO: change to Player
        :param players: A list of Player objects representing the players
        :param rated: Whether the game is rated (ratings change based on outcome)
        """
        # The message created by the bot outside the not-yet-existent thread
        self.status_message = status_message
        # The game type
        self.game_type = game_type
        # Who created the lobby
        self.creator = creator

        random.shuffle(players)  # Randomize player order TODO: rework with introduction of team-based games

        # All players in the game
        self.players = players
        self.rated = rated  # Is the game rated?
        self.thread = None  # The thread object after self.thread_setup() is called
        self.game_message = None  # The message representing the game after self.thread_setup() is called

        self.module = importlib.import_module(GAME_TYPES[game_type][0])  # Game module
        # Game class instantiated with the players
        self.game = getattr(self.module, GAME_TYPES[game_type][1])(self.players)

    async def thread_setup(self) -> None:
        """
        Sets up the game in Discord
        1. Create a private thread off of the channel the bot was called on
        2. Add users to the thread
        3. Send a message to the thread (that is used for the game message)

        Due to an async limitation, this function must be called on the class directly after it is created.
        TODO: change the naming of the thread it is SO BAD OMG
        :return: Nothing
        """

        rated_prefix = "Rated "  # Add "Rated" to the name of the thread if the game
        if not self.rated:
            rated_prefix = ""

        game_thread = await self.status_message.channel.create_thread(  # Create the private thread.
            name=f"{rated_prefix}{self.game_type} game (PlayCord)",
            type=discord.ChannelType.private_thread, invitable=False)  # Don't allow people to add themselves

        for player in self.players:  # Add users to the thread
            await game_thread.add_user(player.user)

        # Temporary embed TODO: remove this and make it cleaner while still guaranteeing the bot gets the first message
        getting_ready_embed = CustomEmbed(title="Almost done!",
                                          description="The game is about to start! This should only take a moment.")

        # Set the thread and game message in the class
        self.thread = game_thread
        self.game_message = await self.thread.send(embed=getting_ready_embed)

    async def move(self, ctx: discord.Interaction, arguments: dict[str, typing.Any]) -> None:
        """
        Make a move. This function is called dynamically by handle_move in the main program.
        How it works:
        1. Call the game's move function
        2. Update the game message based on the changes to the move
        :param ctx: Discord context window
        :param arguments: the list of preparsed arguments to pass directly into the move function
        :return: None
        """
        if ctx.user.id != self.game.current_turn().id:
            message = await ctx.followup.send(content="It isn't your turn right now!", ephemeral=True)
            await message.delete(delay=5)
            return
        self.game.move(arguments)  # Move

        if (outcome := self.game.outcome()) is not None:
            if isinstance(outcome, Player):
                return
            return

        await self.display_game_state()  # Update game state
        message = await ctx.followup.send(content="Move made!", ephemeral=True)
        await message.delete(delay=5)

    async def display_game_state(self) -> None:
        """
        Use the Game class (self.game) to get an updated version of the game state.
        TODO: allow the Game class to provide more than just an image and let it use embed fields and player objects
        :return: None
        """

        # Embed to send as the updated game state
        embed = CustomEmbed(title=f"Playing {self.game_type}",
                            description=textify(TEXTIFY_CURRENT_GAME_TURN,
                                    {"player": self.game.current_turn().mention}))

        picture_bytes = self.game.generate_game_picture()  # Get the bytes of the game state as an image

        # Shenanigans to convert into a discord.File
        image = io.BytesIO()
        image.write(picture_bytes)
        image.seek(0)
        game_picture = discord.File(image, filename="image.png")

        # Add players and image to the embed
        embed.set_image(url="attachment://image.png")
        embed.set_footer(text="bagel.exe is not responding")  #
        embed.add_field(name="Players:", value=convert_to_queued(self.players, self.creator))

        # Edit the game message with the new embed
        await self.game_message.edit(embed=embed, attachments=[game_picture])


class MatchmakingInterface:
    """
    MatchmakingInterface - the class that handles matchmaking for a game, where control is promptly handed off to a GameInterface
    via the successful_matchmaking function.
    """
    def __init__(self, creator: discord.User, game_type: str, message: discord.InteractionMessage, rated: bool):
        # Whether the startup of the matchmaking interaction failed
        self.failed = None

        # Game type
        self.game_type = game_type

        # Creator of the game
        self.creator = creator

        # Is the game rated?
        self.rated = rated

        # Game module
        self.module = importlib.import_module(GAME_TYPES[game_type][0])

        # Start the list of queued players with just the creator
        self.queued_players = [get_player(game_type, creator)]

        # The message context to edit when making updates
        self.message = message

        if self.queued_players == [None]:  # Couldn't get information on the creator, so fail now
            fail_embed = CustomEmbed(title="Couldn't connect to database!", description="The bot failed to connect to the database."
                                                                                  " This is likely a temporary error, try again later!")
            self.failed = fail_embed
            return

        # Game class
        self.game = getattr(self.module, GAME_TYPES[game_type][1])

        # Required and maximum players for game TODO: more complex requirements for start/stop
        self.required_players = self.game.minimum_players
        self.maximum_players = self.game.maximum_players

        self.outcome = None  # Whether the matchmaking was successful (True, None, or False)


    async def callback_ready_game(self, ctx: discord.Interaction) -> None:
        """
        Callback for the selected player to join the game
        :param ctx: discord context
        :return: Nothing
        """
        await ctx.response.defer()  # Prevent button from failing

        if ctx.user.id in [p.id for p in self.queued_players]:  # Can't join if you are already in
            await ctx.followup.send("You are already in the game!", ephemeral=True)
        else:
            new_player = get_player(self.game_type, ctx.user)
            if new_player is None:  # Couldn't retrieve information, so don't join them
                await ctx.followup.send("Couldn't connect to DB!", ephemeral=True)
                return
            self.queued_players.append(new_player)  # Add the player to queued_players
            await self.update_embed()  # Update embed on discord side


    async def callback_start_game(self, ctx: discord.Interaction) -> None:
        """
        Callback for the selected player to start the game.
        :param ctx: Discord context
        :return: Nothing
        """
        await ctx.response.defer()  # Prevent button interaction from failing

        if ctx.user.id != self.creator.id:  # Don't have permissions to start the game
            await ctx.followup.send("You can't start the game (not the creator).", ephemeral=True)
            return

        # The matchmaking was successful!
        self.outcome = True

        # Start the GameInterface
        await successful_matchmaking(self.game_type, self.message, self.creator,
                                     self.queued_players, self.rated)

    async def update_embed(self) -> None:
        """
        Update the embed based on the players in self.players
        :return: Nothing
        """
        # Set up the embed
        embed = CustomEmbed(title="Waiting for players...",
                            description=f"_There are currently {len(self.queued_players)} in the queue._\n"
                                        f"This game ({self.game_type}) /requires at least {self.required_players}"
                                        f" players and at most {self.maximum_players} players.")
        embed.add_field(name="Players:", value=convert_to_queued(self.queued_players, self.creator), inline=False)

        # View for matchmaking buttons

        # Can the start button be pressed?
        start_enabled = self.maximum_players >= len(self.queued_players) >= self.required_players

        view = MatchmakingView(join_button_callback=self.callback_ready_game,
                               leave_button_callback=self.callback_leave_game,
                               start_button_callback=self.callback_start_game,
                               can_start=start_enabled)

        # Update the embed in Discord
        await self.message.edit(embed=embed, view=view)


    async def callback_leave_game(self, ctx: discord.Interaction) -> None:
        """
        Callback for the selected player to leave the matchmaking session
        :param ctx: discord context
        :return: None
        """

        await ctx.response.defer()  # Prevent button interaction from failing

        if ctx.user.id not in [p.id for p in self.queued_players]:  # Can't leave if you weren't even there
            await ctx.followup.send("You aren't in the game!", ephemeral=True)
        else:
            # Remove player from queue
            for player in self.queued_players:
                if player.id == ctx.user.id:
                    self.queued_players.remove(player)
                    break

            # Nobody is left lol
            if not len(self.queued_players):
                await ctx.followup.send("You were the last person in the lobby, so the game was cancelled!", ephemeral=True)
                await self.message.delete()  # Remove matchmaking message
                self.outcome = False
                return

            if ctx.user.id == self.creator.id:  # Update creator if the person leaving was the creator.
                self.creator = self.queued_players[0].user

            await self.update_embed()  # Update embed again
        return




async def successful_matchmaking(game_type: str, message, creator: discord.User, players: list[Player], rated: bool)\
        -> None:
    """
    Callback called by MatchmakingInterface when the game is successfully started
    Sets up and registers a new GameInterface.
    :param game_type: the game type to start
    :param message: the message used for matchmaking by MatchmakingInterface
    :param creator: who created the game
    :param players: a list of players to pass to GameInterface
    :param rated: whether the game is rated
    :return: Nothing
    """

    # Placeholder spectate button TODO: correctly implement
    join_thread_embed = CustomEmbed(title="Game started!", description="ya click button if u want to spectate")
    view = discord.ui.View()
    spectate_button = discord.ui.Button(label="Spectate", style=discord.ButtonStyle.blurple)
    view.add_item(spectate_button)


    # Send the spectate view and embed
    await message.edit(embed=join_thread_embed, view=view)

    # Set up a new GameInterface
    game = GameInterface(game_type, message, creator, players, rated)
    await game.thread_setup()

    # Register the game to the channel it's in TODO: fix bug that allows only one game per channel, too lazy rn
    constants.CURRENT_GAMES.update({game.status_message.channel.id: game})
    constants.CURRENT_THREADS.update({game.thread.id: game.status_message.channel.id})

    await game.display_game_state()  # Send the game display state


async def game_over(final_rankings, rated, thread, outbound_message, ):
    pass


class DynamicButtonView(discord.ui.View):
    def __init__(self, buttons):
        super().__init__(timeout=None)

        for button in buttons:
            for argument in ["label", "style", "id", "emoji", "disabled", "callback"]:
                if argument not in button.keys():
                    if argument == "disabled":
                        button[argument] = False
                        continue
                    button[argument] = None

            item = discord.ui.Button(label=button["label"], style=button["style"],
                                     custom_id=button["id"], emoji=button["emoji"], disabled=button["disabled"])
            if button["callback"] is not None:

                item.callback = button["callback"]
            else:
                item.callback = self._fail_callback
            self.add_item(item)


    async def _fail_callback(self, interaction: discord.Interaction):
        embed = interaction.message.embeds[0] # There can only be one... embed :0
        for child in self.children:  # Disable all children
            child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)  # Update message

        msg = await interaction.followup.send(content="That interaction is no longer active due to a bot restart!"
                                                " Please create a new interaction :)", ephemeral=True)

        await msg.delete(delay=10)





class MatchmakingView(DynamicButtonView):
    def __init__(self, join_button_callback=None, leave_button_callback=None,
                 start_button_callback=None, can_start=True):
        super().__init__([{"label": "Join", "style": discord.ButtonStyle.gray, "id": "join", "callback": join_button_callback},
                          {"label": "Leave", "style": discord.ButtonStyle.gray, "id": "leave", "callback": leave_button_callback},
                          {"label": "Start", "style": discord.ButtonStyle.blurple, "id": "start", "callback": start_button_callback, "disabled": not can_start}])



