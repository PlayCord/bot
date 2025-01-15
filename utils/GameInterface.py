import importlib
import random
import traceback
import typing

import trueskill

from configuration.constants import *
from utils.CustomEmbed import CustomEmbed, ErrorEmbed
from utils.Database import get_player, update_player, update_rankings, update_db_rankings
from utils.Player import Player
from utils.conversion import textify, column_creator, column_names, column_elo, column_turn, player_representative, \
    player_verification_function


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
        self.info_message = None # The message showing game info, whose turn, and what players.
        # also made by self.thread_setup()
        self.module = importlib.import_module(GAME_TYPES[game_type][0])  # Game module
        # Game class instantiated with the players
        self.game = getattr(self.module, GAME_TYPES[game_type][1])(self.players)

        for p in players:
            IN_GAME.update({p: self})

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

    async def move(self, ctx: discord.Interaction, name, arguments: dict[str, typing.Any]) -> None:
        """
        Make a move. This function is called dynamically by handle_move in the main program.
        How it works:
        1. Call the game's move function
        2. Update the game message based on the changes to the move
        :param name: Name of movement function to call
        :param ctx: Discord context window
        :param arguments: the list of preparsed arguments to pass directly into the move function
        :return: None
        """
        if ctx.user.id != self.game.current_turn().id:
            message = await ctx.followup.send(content="It isn't your turn right now!", ephemeral=True)
            await message.delete(delay=5)
            return
        try:
            move_return_value = getattr(self.game, name)(arguments)
        except Exception as e:
            error_embed = ErrorEmbed(what_failed=f"Error occurred while making a move! ({type(e)})", reason=traceback.format_exc())
            await ctx.followup.send(embed=error_embed, ephemeral=True)
            await game_over(self.game_type, traceback.format_exc(), self.players, self.rated, self.thread, self.status_message)
            return
        # TODO: parse move return


        await self.display_game_state()  # Update game state


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
        TODO: allow the Game class to provide more than just an image and let it use embed fields and player objects
        :return: None
        """

        # Embed to send as the updated game state
        info_embed = CustomEmbed(title=f"Playing {self.game.name} with {len(self.players)} players",
                            description=textify(TEXTIFY_CURRENT_GAME_TURN,
                                    {"player": self.game.current_turn().mention})).remove_footer()

        state_embed = CustomEmbed().remove_footer()

        game_state = self.game.state()  # Get the bytes of the game state as an image

        state_types = {}
        limits = {}
        picture = None
        for state_type in game_state:
            state_type._embed_transform(state_embed)
            limits[state_type.type] = state_type.limit
            if state_type.type in state_types:
                state_types[state_type.type] += 1
            else:
                state_types[state_type.type] = 1
            if state_type.type == "image":  # Flag to extract discord.File object from the image type
                picture = state_type.game_picture

        for limit_type in limits:
             if state_types[limit_type] > limits[limit_type]:
                 state_embed = CustomEmbed(title="Error displaying game state!",
                                     description="TODO: add a selector of functionality for this error")




        info_embed.insert_field_at(0, name="Players:", value=column_names(self.players))
        info_embed.add_field(name="Ratings:", value=column_elo(self.players))
        info_embed.add_field(name="Turn:", value=column_turn(self.players, self.game.current_turn()))

        # Edit the game message with the new embed
        await self.info_message.edit(embed=info_embed)
        await self.game_message.edit(embed=state_embed, attachments=[picture])


class MatchmakingInterface:
    """
    MatchmakingInterface - the class that handles matchmaking for a game, where control is promptly handed off to a GameInterface
    via the successful_matchmaking function.
    """
    def __init__(self, creator: discord.User, game_type: str, message: discord.InteractionMessage,
                 rated: bool, private: bool):
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
            fail_embed = CustomEmbed(title="Couldn't connect to database!", description="The bot failed to connect to the database."
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



    async def accept_invite(self, player):
        if player.id in [p.id for p in self.queued_players]:  # Can't join if you are already in
            return "You are already in the game!"
        else:
            new_player = get_player(self.game_type, player)
            if new_player is None:  # Couldn't retrieve information, so don't join them
                return "Couldn't connect to DB!"
            if self.private:
                self.whitelist.add(new_player)
            else:
                try:
                    self.blacklist.remove(new_player)
                except KeyError:
                    pass
            self.queued_players.add(new_player)  # Add the player to queued_players
            IN_MATCHMAKING.update({new_player: self})
            await self.update_embed()  # Update embed on discord side


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

        if kicked: return f"Successfully kicked and banned {player.mention} from the game for reason \"{reason}\""
        return f"Successfully banned {player.mention} from the game for reason \"{reason}\""


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

        if kicked: return f"Successfully kicked {player.mention} from the game for reason \"{reason}\""
        return f"Didn't kick anyone: {player.mention} isn't in this lobby!"


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

        print(IN_MATCHMAKING, self.queued_players)
        # Start the GameInterface
        await successful_matchmaking(self.game_type, self.message, self.creator,
                                     self.queued_players, self.rated)


    async def update_embed(self) -> None:
        """
        Update the embed based on the players in self.players
        :return: Nothing
        """
        # Set up the embed

        game_rated_text = "Rated" if self.rated else "Not Rated"
        private_text = "🔐Private" if self.private else "🔓Public"

        embed = CustomEmbed(title=f"Queueing for {self.game.name}...",
                            description=f"⏰{self.game.time}{LONG_SPACE_EMBED*2}"
                                        f"👤{self.allowed_players}{LONG_SPACE_EMBED*2}"
                                        f"📈{self.game.difficulty}{LONG_SPACE_EMBED*2}"
                                        f"📊{game_rated_text}{LONG_SPACE_EMBED*2}"
                                        f"{private_text}")

        embed.add_field(name="Players:", value=column_names(self.queued_players), inline=True)
        embed.add_field(name="Rating:", value=column_elo(self.queued_players), inline=True)
        embed.add_field(name="Creator:", value=column_creator(self.queued_players, self.creator), inline=True)


        if self.private:
            embed.add_field(name="Whitelist:", value=column_names(list(self.whitelist)), inline=True)
        elif len(self.blacklist):
            embed.add_field(name="Blacklist:", value=column_names(list(self.blacklist)), inline=True)

        embed.add_field(name="Game Info:", value=self.game.description, inline=False)
        embed.add_field(name="Game by:", value=f"[{self.game.author}]({self.game.author_link})\n[Source]({self.game.source_link})")

        # View for matchmaking buttons

        # Can the start button be pressed?
        start_enabled = self.player_verification_function(len(self.queued_players))

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


    for p in players:
        IN_MATCHMAKING.pop(p)

    CURRENT_MATCHMAKING.pop(message.id)


    # Set up a new GameInterface
    game = GameInterface(game_type, message, creator, list(players), rated)  # fix: turn advantageous set to list for gameinterface
    await game.thread_setup()


    # Register the game to the channel it's in
    CURRENT_GAMES.update({game.thread.id: game})


    await message.edit(embed=join_thread_embed, view=SpectateView(spectate_button_id=f"spectate/{game.thread.id}",
                                                                  game_link=game.info_message.jump_url))

    await game.display_game_state()  # Send the game display state


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

    for p in players:
        IN_GAME.pop(p)

    player_ratings = {}
    current_place = 1
    nums_current_place = 0
    matching = 0
    keys = [next(iter(p)) for p in adjusted_rating_groups]
    all_ratings = {list(p.keys())[0]:list(p.values())[0] for p in adjusted_rating_groups}
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

        player_ratings.update({pre_rated_player.id: {"old_rating": round(starting_mu), "delta": mu_delta, "place": current_place, "new_rating": aftermath_mu, "new_sigma": aftermath_sigma}})

    print(player_ratings)
    player_string = "\n".join([f"{player_ratings[p]["place"]}.{LONG_SPACE_EMBED}<@{p}>{LONG_SPACE_EMBED}{player_ratings[p]["old_rating"]}{LONG_SPACE_EMBED}({player_ratings[p]["delta"]})" for p in player_ratings])

    game_over_embed = CustomEmbed(title="Game Over", description="That's the end! Thanks for playing :)")
    game_over_embed.add_field(name="Rankings", value=player_string)

    # Send the embed
    await outbound_message.edit(embed=game_over_embed, view=None)

    await thread.edit(locked=True, archived=True, reason="Game is over.")

    final_ranking_embed = CustomEmbed(title="That's all, folks!", description="Hope you had fun playing :)")
    final_ranking_embed.add_field(name="Final Rankings", value=player_string)

    await thread.send(embed=final_ranking_embed)



    for player_id in player_ratings:
        player_data = player_ratings[player_id]
        update_player(game_type, Player(mu=player_data["new_rating"], sigma=player_data["new_sigma"],
                                        user=discord.Object(id=player_id)))


    update_db_rankings(game_type)


class DynamicButtonView(discord.ui.View):
    """
    Hoo boy
    this is cursed
    "Simple" way of making a button-only persistent view
    Only took 3 hours :)
    """
    def __init__(self, buttons):
        super().__init__(timeout=None)

        for button in buttons:
            for argument in ["label", "style", "id", "emoji", "disabled", "callback", "link"]:
                if argument not in button.keys():
                    if argument == "disabled":
                        button[argument] = False
                        continue
                    button[argument] = None

            item = discord.ui.Button(label=button["label"], style=button["style"],
                                     custom_id=button["id"], emoji=button["emoji"], disabled=button["disabled"],
                                     url=button["link"])
            if button["callback"] is None:
                item.callback = self._fail_callback
            elif button["callback"] == "none":
                item.callback = self._null_callback
            else:
                item.callback = button["callback"]



            self.add_item(item)

    async def _null_callback(self, interaction: discord.Interaction):
        """
        TODO: add logging here. This is a NULL callback
        :param interaction: discord context
        :return:
        """
        pass

    async def _fail_callback(self, interaction: discord.Interaction):
        """
        If a "dead" view is interacted, simply disable each component and update the message
        also send an ephemeral message to the interacter
        :param interaction: discord context
        :return: nothing
        """
        embed = interaction.message.embeds[0] # There can only be one... embed :0
        for child in self.children:  # Disable all children
            child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)  # Update message, because you can't autoupdate

        msg = await interaction.followup.send(content="That interaction is no longer active due to a bot restart!"
                                                " Please create a new interaction :)", ephemeral=True)

        await msg.delete(delay=10)


class MatchmakingView(DynamicButtonView):
    def __init__(self, join_button_callback=None, leave_button_callback=None,
                 start_button_callback=None, can_start=True):
        super().__init__([{"label": "Join", "style": discord.ButtonStyle.gray, "id": "join", "callback": join_button_callback},
                          {"label": "Leave", "style": discord.ButtonStyle.gray, "id": "leave", "callback": leave_button_callback},
                          {"label": "Start", "style": discord.ButtonStyle.blurple, "id": "start", "callback": start_button_callback, "disabled": not can_start}])


class InviteView(DynamicButtonView):
    def __init__(self, join_button_id=None, game_link=None):
        super().__init__([{"label": "Join Game", "style": discord.ButtonStyle.blurple, "id": join_button_id, "callback": "none"},
                          {"label": "Go To Game (won't join)", "style": discord.ButtonStyle.gray, "link": game_link}])


class SpectateView(DynamicButtonView):
    def __init__(self, spectate_button_id=None, game_link=None):
        super().__init__([{"label": "Spectate Game", "style": discord.ButtonStyle.blurple, "id": spectate_button_id, "callback": "none"},
                          {"label": "Go To Game (won't join)", "style": discord.ButtonStyle.gray, "link": game_link}])