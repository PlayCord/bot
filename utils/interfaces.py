import importlib
import inspect
import logging
import random
import traceback
import typing

import trueskill

from configuration.constants import *
from utils.Game import Game
from utils.embeds import CustomEmbed, ErrorEmbed, GameOverviewEmbed
from utils.database import get_player, update_player, update_db_rankings
from utils.Player import Player
from utils.conversion import textify, column_creator, column_names, column_elo, column_turn, player_representative, \
    player_verification_function, contextify
from utils.views import MatchmakingView, SpectateView


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
        self.thread = None  # The thread object after self.setup() is called
        self.game_messages = []  # The message representing the game after self.setup() is called
        self.info_messages = [] # The message showing game info, whose turn, and what players.
        # also made by self.setup()
        self.module = importlib.import_module(GAME_TYPES[game_type][0])  # Game module
        # Game class instantiated with the players
        self.game = getattr(self.module, GAME_TYPES[game_type][1])(self.players)

        self.current_turn = None

        for p in players:
            IN_GAME.update({p: self})

    async def setup(self) -> None:
        """
        Sets up the game in Discord
        1. Create a private thread off of the channel the bot was called on
        2. Add users to the thread
        3. Send a message to the thread (that is used for the game message)

        Due to an async limitation, this function must be called on the class directly after it is created.
        :return: Nothing
        """

        rated_prefix = "Rated "  # Add "Rated" to the name of the thread if the game
        if not self.rated:
            rated_prefix = ""

        game_thread = await self.status_message.channel.create_thread(  # Create the private thread.
            name=f"{rated_prefix}{self.game.name} game ({NAME})",
            type=discord.ChannelType.private_thread, invitable=False)  # Don't allow people to add themselves

        for player in self.players:  # Add users to the thread
            await game_thread.add_user(player.user)


        game_info_embed = CustomEmbed(description="<a:loading:1318216218116620348>").remove_footer()
        # Temporary embed TODO: remove this and make it cleaner while still guaranteeing the bot gets the first message
        getting_ready_embed = CustomEmbed(description="<a:loading:1318216218116620348>").remove_footer()

        # Set the thread and game message in the class
        self.thread = game_thread
        self.info_message = await self.thread.send(embed=game_info_embed)
        self.game_message = await self.thread.send(embed=getting_ready_embed)

    async def move_by_command(self, ctx: discord.Interaction, name, arguments: dict[str, typing.Any], current_turn_required: bool = True) -> None:
        """
        Make a move by command. This function is called dynamically by handle_move in the main program.
        How it works:
        1. Call the game's move function
        2. Update the game message based on the changes to the move
        :param name: Name of movement function to call
        :param ctx: Discord context window
        :param arguments: the list of preparsed arguments to pass directly into the move function
        :return: None
        """
        self.current_turn = self.game.current_turn()
        if ctx.user.id != self.current_turn.id and current_turn_required:
            message = await ctx.followup.send(content="It isn't your turn right now!", ephemeral=True)
            await message.delete(delay=5)
            return
        try:
            move_return_value = getattr(self.game, name)(get_player(self.game_type, ctx.user), **arguments)  # TODO: add multiple types of return data for this
        except Exception as e:
            error_embed = ErrorEmbed(ctx, what_failed=f"Error occurred while making a move! ({type(e)})", reason=traceback.format_exc())
            await ctx.followup.send(embed=error_embed, ephemeral=True)
            await game_over(self.game_type, traceback.format_exc(), self.players, self.rated, self.thread, self.status_message)
            return

        # if move_return_value is None:  # No return value, therefore this was a

        await self.display_game_state()  # Update game state

        if (outcome := self.game.outcome()) is not None:  # Game is over

            message = await ctx.followup.send(content="Game over!", ephemeral=True)
            await message.delete(delay=5)
            await game_over(self.game_type, outcome, self.players, self.rated, self.thread, self.status_message)
            return



        message = await ctx.followup.send(content="Move made!", ephemeral=True)
        await message.delete(delay=5)

    async def move_by_button(self, ctx: discord.Interaction, name, arguments: dict[str, typing.Any], current_turn_required: bool = True) -> None:
        """
        Callback for a move triggered by a button. This function is called dynamically by
        game_button_callback in the main program.
        :param ctx: discord Context for button interaction
        :param name: Name of game function to callback
        :param arguments: arguments to pass directly into the button function
        :param current_turn_required: whether the current turn is required for the button click
        :return: Nothing
        """
        # Update current turn
        self.current_turn = self.game.current_turn()

        # Check to make sure that it is current turn (if required)
        if ctx.user.id != self.current_turn.id and current_turn_required:
            message = await ctx.followup.send(content="It isn't your turn right now!", ephemeral=True)
            await message.delete(delay=5)
            return

        # Get callback
        callback_function = getattr(self.game, name)

        # Get signature
        signature = inspect.signature(callback_function).parameters

        # Convert str to int and float if required
        type_converted_arguments = {}
        for arg in arguments:
            argument_type = signature[arg].annotation
            if argument_type is int:
                type_converted_arguments[arg] = int(arguments[arg])
            elif argument_type is float:
                type_converted_arguments[arg] = float(arguments[arg])
            else:
                type_converted_arguments[arg] = arguments[arg]

        # Get return value of move
        move_return_value = callback_function(get_player(self.game_type, ctx.user),
                                              **type_converted_arguments)

        # Update display painting
        await self.display_game_state()

        if (outcome := self.game.outcome()) is not None:  # Game is over

            message = await ctx.followup.send(content="Game over!", ephemeral=True)
            await message.delete(delay=5)
            await game_over(self.game_type, outcome, self.players, self.rated, self.thread, self.status_message)
            return



        message = await ctx.followup.send(content="Move made!", ephemeral=True)
        await message.delete(delay=5)

    async def display_game_state(self) -> None:
        """
        Use the Game class (self.game) to get an updated version of the game state.
        :return: None
        """
        log = logging.getLogger("playcord.game.display_game_state")
        self.current_turn = self.game.current_turn()
        # Embed to send as the updated game state
        info_embed = CustomEmbed(title=f"Playing {self.game.name} with {len(self.players)} players",
                            description=textify(TEXTIFY_CURRENT_GAME_TURN,
                                    {"player": self.current_turn.mention})).remove_footer()

        # Game state embed and view
        state_embed = CustomEmbed().remove_footer()
        state_view = discord.ui.View()

        game_state = self.game.state()  # Get the game state from the game

        state_types = {}
        limits = {}
        picture = None

        removed_fields = 0
        for state_type in game_state:

            # Call transformation functions if they exist
            if hasattr(state_type, "_embed_transform"):
                state_type._embed_transform(state_embed)
                if len(state_embed.fields) >= 25:
                    for remove_index in range(25, len(state_embed.fields)):
                        state_embed.remove_field(remove_index)
                removed_fields += len(state_embed.fields) - 25
            if hasattr(state_type, "_view_transform"):
                state_type._view_transform(state_view, self.thread.id)

            limits[state_type.type] = state_type.limit  # Add limit for the state type, regardless of if it exists

            # Keep track of the amount of each state type
            if state_type.type in state_types:
                state_types[state_type.type] += 1
            else:
                state_types[state_type.type] = 1

            if state_type.type == "image":  # Special flag to extract discord.File object from the image type
                picture = state_type.game_picture

        # Detect if over limit
        if removed_fields > 0:
            log.warning(f"Had to discard {removed_fields} fields from processing due to being over the limit!"
                        f" This could cause a bad paint. game_id={self.thread.id} game_type={self.game_type}")

        for limit_type in limits:
             if state_types[limit_type] > limits[limit_type]:
                log.warning(f"Unsure method determined that state type {limit_type!r}"
                            f" was over the limit ({state_types[limit_type]} > {limits[limit_type]})"
                            f" game_id={self.thread.id} game_type={self.game_type}")


        # Add info embed data
        info_embed.add_field(name="Players:", value=column_names(self.players))
        info_embed.add_field(name="Ratings:", value=column_elo(self.players))
        info_embed.add_field(name="Turn:", value=column_turn(self.players, self.current_turn))

        # Edit the game and info messages with the new embeds
        await self.info_message.edit(embed=info_embed)

        if picture is not None:  # For some reason, [None] is not accepted by discord.py, so send it None if no image.
            attachments = [picture]
        else:
            attachments = []

        await self.game_message.edit(embed=state_embed, view=state_view, attachments=attachments)

        # Edit overview embed with new data
        await self.status_message.edit(embed=GameOverviewEmbed(self.game.name, self.rated, self.players, self.current_turn))


class MatchmakingInterface:
    """
    MatchmakingInterface - the class that handles matchmaking for a game, where control is promptly handed off to a GameInterface
    via the successful_matchmaking function.
    """
    def __init__(self, creator: discord.User, game_type: str, message: discord.InteractionMessage,
                 rated: bool, private: bool):

        self.logger = logging.getLogger("playcord.matchmaking_interface")

        # Whether the startup of the matchmaking interaction failed
        self.failed = None

        # Game type
        self.game_type = game_type

        # Creator of the game
        self.creator = creator

        # Is the game rated?
        self.rated = rated

        # Whether joining the game is open
        self.private = private

        # Allowed players for whitelist
        self.whitelist = {get_player(game_type, creator)}

        # Disallowed players (blacklist
        self.blacklist = set()

        # Game module
        self.module = importlib.import_module(GAME_TYPES[game_type][0])

        # Start the list of queued players with just the creator
        self.queued_players = set(self.whitelist)

        # The message context to edit when making updates
        self.message = message

        if self.queued_players == {None}:  # Couldn't get information on the creator, so fail now
            fail_embed = ErrorEmbed(what_failed="Couldn't connect to database!",
                                    reason="The bot failed to connect to the database."
                                                                                  " This is likely a temporary error, try again later!")
            self.failed = fail_embed
            return
        CURRENT_MATCHMAKING.update({self.message.id: self})
        IN_MATCHMAKING.update({p: self for p in self.queued_players})

        # Game class
        self.game = getattr(self.module, GAME_TYPES[game_type][1])

        # Required and maximum players for game TODO: more complex requirements for start/stop
        self.player_verification_function = player_verification_function(self.game.players)
        self.allowed_players = player_representative(self.game.players)

        self.outcome = None  # Whether the matchmaking was successful (True, None, or False)

    async def update_embed(self) -> None:
        """
        Update the embed based on the players in self.players
        :return: Nothing
        """
        # Set up the embed

        game_rated_text = "Rated" if self.rated else "Not Rated"
        private_text = "🔐Private" if self.private else "🔓Public"

        # Parameters in embed title:
        # Time
        # Allowed players
        # Difficulty
        # Rated/Unrated
        # Public/Private

        embed = CustomEmbed(title=f"Queueing for {self.game.name}...",
                            description=f"⏰{self.game.time}{LONG_SPACE_EMBED*2}"
                                        f"👤{self.allowed_players}{LONG_SPACE_EMBED*2}"
                                        f"📈{self.game.difficulty}{LONG_SPACE_EMBED*2}"
                                        f"📊{game_rated_text}{LONG_SPACE_EMBED*2}"
                                        f"{private_text}")


        # Add columns for names, elo, and creator status
        embed.add_field(name="Players:", value=column_names(self.queued_players), inline=True)
        embed.add_field(name="Rating:", value=column_elo(self.queued_players), inline=True)
        embed.add_field(name="Creator:", value=column_creator(self.queued_players, self.creator), inline=True)

        # Add whitelist or blacklist depending on private status
        if self.private:
            embed.add_field(name="Whitelist:", value=column_names(self.whitelist), inline=True)
        elif len(self.blacklist):
            embed.add_field(name="Blacklist:", value=column_names(self.blacklist), inline=True)

        # Credits for game
        embed.add_field(name="Game Info:", value=self.game.description, inline=False)
        embed.add_field(name="Game by:", value=f"[{self.game.author}]({self.game.author_link})\n[Source]({self.game.source_link})")

        # Can the start button be pressed?
        start_enabled = self.player_verification_function(len(self.queued_players))

        # Create matchmaking button view (with callbacks and can_start)
        view = MatchmakingView(join_button_callback=self.callback_ready_game,
                               leave_button_callback=self.callback_leave_game,
                               start_button_callback=self.callback_start_game,
                               can_start=start_enabled)

        # Update the embed in Discord
        await self.message.edit(embed=embed, view=view)

    async def accept_invite(self, ctx: discord.Interaction) -> bool:
        """
        Accept a invite.
        :param ctx: discord context with information about the invite
        :return: whether the invite succeeded or failed
        """
        player = ctx.user
        log = self.logger.getChild("accept_invite")
        if player.id in [p.id for p in self.queued_players]:  # Can't join if you are already in
            log.debug(f"Player {player.id} ({player.name}) attempted to accept invite, but they are already in the game! "
                      f"{contextify(ctx)}")
            await ctx.followup.send("You are already in the game!", ephemeral=True)
            return False
        else:
            new_player = get_player(self.game_type, player)
            if new_player is None:  # Couldn't retrieve information, so don't join them
                log.warning(
                    f"Player {player.id} ({player.name}) attempted to accept invite, but we couldn't connect to the database!"
                    f"{contextify(ctx)}")
                await ctx.followup.send("Couldn't connect to DB!", ephemeral=True)
                return False
            if self.private:
                self.whitelist.add(new_player)
            else:
                try:
                    self.blacklist.remove(new_player)
                except KeyError:
                    pass
            self.queued_players.add(new_player)  # Add the player to queued_players
            IN_MATCHMAKING.update({new_player: self})
            log.debug(
                f"Successfully accepted invite for {player.id} ({player.name})!"
                f"{contextify(ctx)}")
            await self.update_embed()  # Update embed on discord side
        return True

    async def ban(self, player, reason):
        new_player = get_player(self.game_type, player)
        if new_player is None:  # Couldn't retrieve information, so don't join them
            return "Couldn't connect to DB!"

        # Kick if already in and update embed
        kicked = False
        if new_player.id in [p.id for p in self.queued_players]:
            kicked = True
            self.queued_players.remove(new_player)
            IN_MATCHMAKING.pop(new_player)

        # end game if necessary
        if not len(self.queued_players):
            await self.message.delete()  # Remove matchmaking message
            self.outcome = False
            return "idk why you banned yourself when you are the only one in the lobby, lol"

        if player.id == self.creator.id:  # Update creator if the person leaving was the creator.
            self.creator = next(iter(self.queued_players)).user

        # If private game: remove from whitelist
        # If public game: add to blacklist
        if self.private:
            try:
                self.whitelist.remove(new_player)
            except KeyError:
                return "Can't ban someone who isn't on the whitelist anyway!"
        else:
            self.blacklist.add(new_player)

        await self.update_embed()  # Update embed now that we have done all operations

        if kicked: return f"Successfully kicked and banned {player.mention} from the game for reason {reason!r}"
        return f"Successfully banned {player.mention} from the game for reason {reason!r}"

    async def kick(self, player, reason):



        new_player = get_player(self.game_type, player)
        if new_player is None:  # Couldn't retrieve information, so don't join them
            return "Couldn't connect to DB!"

        kicked = False
        if new_player.id in [p.id for p in self.queued_players]:  # Kick if already in
            kicked = True
            self.queued_players.remove(new_player)
            IN_MATCHMAKING.pop(new_player)
            await self.update_embed()

        # end game if necessary
        if not len(self.queued_players):
            await self.message.delete()  # Remove matchmaking message
            self.outcome = False
            return ("idk why you thought kicking yourself was a smart idea "
                    "when you are the only one in the lobby, lol")

        if player.id == self.creator.id:  # Update creator if the person leaving was the creator.
            self.creator = next(iter(self.queued_players)).user

        if kicked: return f"Successfully kicked {player.mention} from the game for reason {reason!r}"
        return f"Didn't kick anyone: {player.mention} isn't in this lobby!"

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
            if not self.private:
                if new_player in self.blacklist:
                    await ctx.followup.send(f"You are banned from this game!"
                                            f" Ask the owner of the game {self.creator.mention}"
                                            f" to unban you!", ephemeral=True)
                    return
                self.queued_players.add(new_player)  # Add the player to queued_players
                IN_MATCHMAKING.update({new_player: self})
                await self.update_embed()  # Update embed on discord side
            else:
                if new_player not in self.whitelist:
                    await ctx.followup.send("You are not on the whitelist for this private game!", ephemeral=True)
                    return
                self.queued_players.add(new_player)  # Add the player to queued_players
                IN_MATCHMAKING.update({new_player: self})
                await self.update_embed()  # Update embed on discord side

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
                    IN_MATCHMAKING.pop(player)
                    break
            # Nobody is left lol
            if not len(self.queued_players):
                await ctx.followup.send("You were the last person in the lobby, so the game was cancelled!", ephemeral=True)
                await self.message.delete()  # Remove matchmaking message
                self.outcome = False
                return

            if ctx.user.id == self.creator.id:  # Update creator if the person leaving was the creator.
                self.creator = next(iter(self.queued_players)).user

            await self.update_embed()  # Update embed again
        return

    async def callback_start_game(self, ctx: discord.Interaction) -> None:
        """
        Callback for the selected player to start the game.
        :param ctx: Discord context
        :return: Nothing
        """
        log = self.logger.getChild("start_game")
        log.debug(f"Attempting to start the game... {contextify(ctx)}")
        await ctx.response.defer()  # Prevent button interaction from failing

        if ctx.user.id != self.creator.id:  # Don't have permissions to start the game
            await ctx.followup.send("You can't start the game (not the creator).", ephemeral=True)
            log.debug(f"Game failed to start because player {ctx.user.id} ({ctx.user.name}) was not the creator. "
                      f"{contextify(ctx)}")
            return

        # The matchmaking was successful!
        self.outcome = True

        log.debug(f"Game successfully started by {ctx.user.id} ({ctx.user.name})!"
                  f"{contextify(ctx)}")
        # Start the GameInterface

        await self.message.edit(embed=CustomEmbed(description="<a:loading:1318216218116620348>").remove_footer(), view=None)
        await successful_matchmaking(game_type=self.game_type, game_class=self.game, message=self.message, creator=self.creator,
                                     players=self.queued_players, rated=self.rated)



async def successful_matchmaking(game_type: str, game_class: Game, message, creator: discord.User, players: set[Player], rated: bool)\
        -> None:
    """
    Callback called by MatchmakingInterface when the game is successfully started
    Sets up and registers a new GameInterface.
    :param game_class: the uninstantiated Game class that will be played, used
    :param game_type: the game type to start
    :param message: the message used for matchmaking by MatchmakingInterface
    :param creator: who created the game
    :param players: a list of players to pass to GameInterface
    :param rated: whether the game is rated
    :return: Nothing
    """

    # Placeholder spectate button
    join_thread_embed = GameOverviewEmbed(game_name=game_class.name,
                                          rated=rated,
                                          players=players,
                                          turn=None)



    for p in players:
        IN_MATCHMAKING.pop(p)

    CURRENT_MATCHMAKING.pop(message.id)


    # Set up a new GameInterface
    game = GameInterface(game_type, message, creator, list(players), rated)  # fix: turn advantageous set to list for gameinterface
    await game.setup()


    # Register the game to the channel it's in
    CURRENT_GAMES.update({game.thread.id: game})


    await message.edit(embed=join_thread_embed, view=SpectateView(spectate_button_id=f"spectate/{game.thread.id}",
                                                                  peek_button_id=f"peek/{game.thread.id}/{game.game_message.id}",
                                                                  game_link=game.info_message.jump_url))


    await game.display_game_state()  # Send the game display state



async def rating_groups_to_string(rankings, groups):
    player_ratings = {}
    current_place = 1
    nums_current_place = 0
    matching = 0
    keys = [next(iter(p)) for p in groups]
    all_ratings = {list(p.keys())[0]: list(p.values())[0] for p in groups}
    for i, pre_rated_player in enumerate(keys):
        if rankings[i] == matching:
            nums_current_place += 1
        else:
            current_place += nums_current_place
            matching = rankings[i]
            nums_current_place = 1

        starting_mu, starting_sigma = pre_rated_player.mu, pre_rated_player.sigma
        aftermath_mu, aftermath_sigma = all_ratings[pre_rated_player].mu, all_ratings[pre_rated_player].sigma

        mu_delta = str(round(aftermath_mu - starting_mu))
        if not mu_delta.startswith("-"):
            mu_delta = "+" + mu_delta

        player_ratings.update({pre_rated_player.id: {"old_rating": round(starting_mu), "delta": mu_delta,
                                                     "place": current_place, "new_rating": aftermath_mu,
                                                     "new_sigma": aftermath_sigma}})

    player_string = "\n".join([
                                  f"{player_ratings[p]["place"]}.{LONG_SPACE_EMBED}<@{p}>{LONG_SPACE_EMBED}{player_ratings[p]["old_rating"]}{LONG_SPACE_EMBED}({player_ratings[p]["delta"]})"
                                  for p in player_ratings])

    return player_string, player_ratings


async def non_rated_groups_to_string(rankings, groups):
    return rankings + "\n" + groups


async def game_over(game_type, outcome, players, rated, thread: discord.Thread, outbound_message):
    # TODO: implement outbound game over view

    sigma = MU * GAME_TRUESKILL[game_type]["sigma"]
    beta = MU * GAME_TRUESKILL[game_type]["beta"]
    tau = MU * GAME_TRUESKILL[game_type]["tau"]
    draw = GAME_TRUESKILL[game_type]["draw"]

    # mpmath backend = near infinite floating point precision
    environment = trueskill.TrueSkill(mu=MU, sigma=sigma, beta=beta, tau=tau, draw_probability=draw,
                                      backend="mpmath")
    # Two cases implemented:

    if isinstance(outcome, str):  # Error
        game_over_embed = ErrorEmbed(what_failed="Error during a move!", reason=outcome)
        # Send the embed
        await outbound_message.edit(embed=game_over_embed)
        await thread.edit(locked=True, archived=True, reason="Game crashed.")
        await thread.send(embed=game_over_embed)
        return

    if rated:

        if isinstance(outcome, Player):  # Somebody won, everybody else lost. No way of comparison (tic-tac-toe)
            # Winner's rating
            winner = environment.create_rating(outcome.mu, outcome.sigma)

            # All the losers
            losers = [{p: environment.create_rating(p.mu, p.sigma)} for p in players if p != outcome]

            rating_groups = [{outcome: winner}, *losers]  # Make the rating groups
            rankings = [0, *[1 for _ in range(len(players) - 1)]]  # Rankings = [0, 1, 1, ..., 1] for this case

        elif isinstance(outcome, list):  # More generic position placement
            # Format:
            # [[p1, p2], [p3], [p4]] indicates p1 and p2 tied, p3 got third, p4 got fourth
            # What if there are teams? screw you

            current_ranking = 0
            rankings = []
            rating_groups = []
            for placement in outcome:
                for player in placement:
                    rankings.append(current_ranking)
                    rating_groups.append({player: environment.create_rating(player.mu, player.sigma)})
                current_ranking += 1

        adjusted_rating_groups = environment.rate(rating_groups=rating_groups, ranks=rankings)

        player_string, player_ratings = await rating_groups_to_string(rankings, adjusted_rating_groups)
    else:  # Non-rated game
        if isinstance(outcome, Player):
            groups = [outcome, *[p for p in players]]  # Make the rating groups
            rankings = [0, *[1 for _ in range(len(players) - 1)]]  # Rankings = [0, 1, 1, ..., 1] for this case

        elif isinstance(outcome, list):
            current_ranking = 0
            rankings = []
            groups = []
            for placement in outcome:
                for player in placement:
                    rankings.append(current_ranking)
                    groups.append(player)
                current_ranking += 1

        player_string = rating_groups_to_string(rankings, groups)



    for p in players:
        IN_GAME.pop(p)


    game_over_embed = CustomEmbed(title="Game Over", description="That's the end! Thanks for playing :)")
    game_over_embed.add_field(name="Rankings", value=player_string)

    # Send the embed
    await outbound_message.edit(embed=game_over_embed, view=None)

    await thread.edit(locked=True, archived=True, reason="Game is over.")

    final_ranking_embed = CustomEmbed(title="That's all, folks!", description="Hope you had fun playing :)")
    final_ranking_embed.add_field(name="Final Rankings", value=player_string)

    await thread.send(embed=final_ranking_embed)

    if rated:
        for player_id in player_ratings:
            player_data = player_ratings[player_id]
            update_player(game_type, Player(mu=player_data["new_rating"], sigma=player_data["new_sigma"],
                                            user=discord.Object(id=player_id)))

        update_db_rankings(game_type)