import asyncio
import importlib
import logging
import random
import sys
import time
import traceback
import typing
from typing import Any

from discord import AppCommandOptionType, app_commands
from discord.app_commands import Choice, Group
from discord.app_commands.transformers import RangeTransformer
from ruamel.yaml import YAML

import configuration.constants as constants
from api.Command import Command
from configuration.constants import *
from utils import database
from utils.analytics import Timer
from utils.conversion import contextify
from utils.embeds import CustomEmbed, ErrorEmbed
from utils.formatter import Formatter
from utils.interfaces import GameInterface, MatchmakingInterface
from utils.views import InviteView

logging.getLogger("discord").setLevel(logging.INFO)  # Discord.py logging level - INFO (don't want DEBUG)

logging.basicConfig(level=logging.DEBUG)

# Configure root logger
root_logger = logging.getLogger("root")
root_logger.setLevel(logging.DEBUG)

# create console handler with a higher log level
ch = logging.StreamHandler(stream=sys.stdout)
ch.setLevel(logging.DEBUG)

ch.setFormatter(Formatter())  # custom formatter
root_logger.handlers = [ch]  # Make sure to not double print

log = logging.getLogger(LOGGING_ROOT)  # Base logger
startup_logger = log.getChild("startup")

startup_logger.info(f"Welcome to {NAME} by @quantumbagel!")
startup_initial_time = time.time()

if __name__ != "__main__":
    startup_logger.critical(ERROR_IMPORTED)
    sys.exit(1)


def load_configuration() -> dict | None:
    """
    Load configuration from constants.CONFIG_FILE
    :return: the configuration as a dictionary
    """
    begin_load_config = time.time()
    try:
        loaded_config_file = YAML().load(open(CONFIG_FILE))
    except FileNotFoundError:
        startup_logger.critical("Configuration file not found.")
        return
    startup_logger.debug(
        f"Successfully loaded configuration file in {round((time.time() - begin_load_config) * 100, 4)}ms!")
    return loaded_config_file


config = load_configuration()
if config is None:
    sys.exit(1)
constants.CONFIGURATION = config  # Set global configuration

database_startup_time = time.time()
database_startup = database.startup()  # Start up the database
if not database_startup:  # Database better work lol
    startup_logger.critical("Database failed to connect on startup!")
    sys.exit(1)
else:
    startup_logger.info(f"Database startup completed in {round((time.time() - database_startup_time) * 100, 4)}ms.")

client = discord.Client(intents=discord.Intents.all())  # Create the client with all intents, so we can read messages
tree = app_commands.CommandTree(client)  # Build command tree

# Root command registration
command_root = app_commands.Group(name=LOGGING_ROOT, description="PlayCord command group. ChangeME", guild_only=True)
play = app_commands.Group(name="play", description="Play all da games here", guild_only=True)


async def send_simple_embed(ctx: discord.Interaction, title: str, description: str, ephemeral: bool = True,
                            responded: bool = False) -> None:
    """
    Generate a simple embed
    :param ephemeral: whether it should be invisible ephemeral or not
    :param ctx: discord context
    :param responded: has interaction been responded to?
    :param title: the title
    :param description: the description
    :return: nothing
    """
    if not responded:
        await ctx.response.send_message(embed=CustomEmbed(title=title, description=description), ephemeral=ephemeral)
    else:
        # Use the followup for sending the embed simply because ctx.response won't work
        await ctx.followup.send(embed=CustomEmbed(title=title, description=description), ephemeral=ephemeral)


async def interaction_check(ctx: discord.Interaction) -> bool:
    """
    Returns if an interaction should be allowed.
    This checks for:
    * Bot user
    * DM
    * Role permission / positioning if no role set
    :param ctx: the Interaction to checker
    :return: true or false
    """
    logger = log.getChild("is_allowed")

    if not IS_ACTIVE:  # Bot disabled via message command
        await send_simple_embed(ctx, "Bot has been disabled!", f"{NAME} "
                                                               f"has been temporarily disabled by a bot owner. This"
                                                               " is likely due to a critical bug or exploit being discovered.")
        logger.warning("Interaction attempted when bot was disabled. " + contextify(ctx))
        return False

    if ctx.user.bot:  # We don't want any bots
        logger.warning("Bot users are not allowed to use commands.")
        return False

    return True


async def command_error(ctx: discord.Interaction, error_message):
    f_log = log.getChild("error")
    f_log.warning(f"Exception in command: {error_message} {contextify(ctx)}")
    await ctx.response.send_message(embed=ErrorEmbed(ctx=ctx,
                                                     what_failed=f"While running the command {ctx.command.name!r}, there was an error {error_message!r}",
                                                     reason=traceback.format_exc()), ephemeral=True)


command_root.error(command_error)
command_root.interaction_check = interaction_check  # Set the interaction check
play.interaction_check = interaction_check
play.error(command_error)


@client.event
async def on_interaction(ctx: discord.Interaction) -> None:
    """
    Callback activated after every bot interaction. For the purposes of this bot,
     this is used to handle button interactions.
    :param ctx:
    :return:
    """
    # Log interaction
    log.getChild("event.on_interaction").debug(f"Interaction received: {contextify(ctx)}")

    custom_id = ctx.data.get("custom_id")  # Get custom ID
    if custom_id is None:  # Not button
        return
    if custom_id.startswith("join/") or custom_id.startswith("leave/") or custom_id.startswith("start/"):
        await matchmaking_button_callback(ctx)
    if custom_id.startswith("select_c/"):
        await game_select_callback(ctx, current_turn_required=True)
    if custom_id.startswith("select_n/"):
        await game_select_callback(ctx, current_turn_required=False)
    if custom_id.startswith("c/"):  # Game view button: turn required
        await game_button_callback(ctx, current_turn_required=True)
    if custom_id.startswith("n/"):  # Game view button: turn not required
        await game_button_callback(ctx, current_turn_required=False)
    if custom_id.startswith("invite/"):  # Invite accept button
        await invite_accept_callback(ctx)
    if custom_id.startswith("spectate/"):  # Spectate button
        await spectate_callback(ctx)
    if custom_id.startswith("peek/"):
        await peek_callback(ctx)


@client.event
async def on_ready() -> None:
    """
    Callback activated after the bot is ready (connected to gateway).
    Only things we need to do is register button views and rich presence.
    :return:
    """
    global startup_initial_time

    if startup_initial_time:
        startup_logger.info(f"Client connected after {round((time.time() - startup_initial_time) * 100, 4)}ms.")
        startup_initial_time = 0  # To prevent reconnects showing this message

    client.loop.create_task(presence())  # Register presence


@client.event
async def on_message(msg: discord.Message) -> None:
    """
    Handle message commands

    playcord/sync
    playcord/sync this
    playcord/sync <id>
    playcord/disable
    playcord/toggle
    playcord/enable
    playcord/clear
    playcord/clear this
    playcord/clear <id>

    :param msg: The message
    :return: None
    """
    global IS_ACTIVE
    f_log = log.getChild("event.on_message")

    # Message synchronization command
    if msg.author.bot:
        return

    if msg.channel.id in CURRENT_GAMES:
        try:
            await msg.delete()
        except discord.Forbidden or discord.NotFound:
            pass
        return

    if msg.content.startswith(f"{LOGGING_ROOT}/") and msg.author.id in OWNERS:
        f_log.info(f"Received potential authorized message command {msg.content!r}.")

    if msg.content.startswith(f"{LOGGING_ROOT}/{MESSAGE_COMMAND_SYNC}") and msg.author.id in OWNERS:  # Perform sync
        split = msg.content.split()
        if len(split) == 1:  # just /sync
            try:
                await tree.sync()
            except discord.app_commands.errors.CommandSyncFailure as e:
                await msg.add_reaction(MESSAGE_COMMAND_FAILED)
                await msg.reply(
                    embed=ErrorEmbed(what_failed=f"Couldn't sync commands! ({type(e)})", reason=traceback.format_exc()))
                return
            f_log.info(f"Performed authorized sync from user {msg.author.id} to all guilds.")
        else:
            if split[1] == MESSAGE_COMMAND_SPECIFY_LOCAL_SERVER:  # sync this
                g = msg.guild
            else:
                try:
                    g = discord.Object(id=int(split[1]))  # sync 983459383
                except ValueError:
                    return

            # Actually sync
            tree.copy_global_to(guild=g)
            try:
                await tree.sync(guild=g)
            except discord.app_commands.errors.CommandSyncFailure as e:  # Something went wrong
                await msg.add_reaction(MESSAGE_COMMAND_FAILED)
                await msg.reply(
                    embed=ErrorEmbed(what_failed=f"Couldn't sync commands! ({type(e)})", reason=traceback.format_exc()))
                return
            f_log.info(f"Performed authorized sync from user {msg.author.id} to guild {g.name!r} (id={g.id!r})")
        await msg.add_reaction(MESSAGE_COMMAND_SUCCEEDED)  # leave confirmation
        return

    # Disable
    elif msg.content == f"{LOGGING_ROOT}/{MESSAGE_COMMAND_DISABLE}" and msg.author.id in OWNERS:  # Disable bot
        if not IS_ACTIVE:
            await msg.add_reaction(MESSAGE_COMMAND_FAILED)  # Don't need to disable
            return
        IS_ACTIVE = False
        f_log.critical(f"Bot has been disabled by authorized user {msg.author.id}.")

        await msg.add_reaction(MESSAGE_COMMAND_SUCCEEDED)  # leave confirmation
        return

    # Enable
    elif msg.content == f"{LOGGING_ROOT}/{MESSAGE_COMMAND_ENABLE}" and msg.author.id in OWNERS:  # Enable bot
        if IS_ACTIVE:
            await msg.add_reaction(MESSAGE_COMMAND_FAILED)  # Don't need to disable
            return
        IS_ACTIVE = True
        f_log.critical(f"Bot has been enabled by authorized user {msg.author.id}.")
        await msg.add_reaction(MESSAGE_COMMAND_SUCCEEDED)  # leave confirmation
        return

    # Toggle
    elif msg.content == f"{LOGGING_ROOT}/{MESSAGE_COMMAND_TOGGLE}" and msg.author.id in OWNERS:  # Toggle bot
        IS_ACTIVE = not IS_ACTIVE
        if IS_ACTIVE:
            f_log.critical(f"Bot has been enabled by authorized user {msg.author.id}.")
            await msg.add_reaction(MESSAGE_COMMAND_SUCCEEDED)  # leave confirmation
        else:
            f_log.critical(f"Bot has been disabled by authorized user {msg.author.id}.")
            await msg.add_reaction(MESSAGE_COMMAND_SUCCEEDED)
        return

    # Clear command tree
    elif msg.content.startswith(f"{LOGGING_ROOT}/{MESSAGE_COMMAND_CLEAR}") and msg.author.id in OWNERS:
        split = msg.content.split()
        if len(split) == 1:
            tree.clear_commands(guild=None)
            await tree.sync()
            f_log.info(f"Performed authorized command tree clear from user {msg.author.id} "
                       f"to all guilds.")
        else:
            if split[1] == MESSAGE_COMMAND_SPECIFY_LOCAL_SERVER:
                g = msg.guild
            else:
                g = discord.Object(id=int(split[1]))
            print(g)
            tree.clear_commands(guild=g)
            # tree.copy_global_to(guild=g)
            await tree.sync(guild=g)
            f_log.info(f"Performed authorized command tree clear from user {msg.author.id} "
                       f"to guild {g.name!r} (id={g.id!r})")
        await msg.add_reaction(MESSAGE_COMMAND_SUCCEEDED)  # leave confirmation
        return


@client.event
async def on_guild_join(guild: discord.Guild) -> None:
    """
    Send a message to guilds when the bot is added.
    :param guild: the guild the bot was added to
    :return: nothing
    """
    f_log = log.getChild("event.guild_join")
    f_log.info(f"Added to guild {guild.name!r} ! (id={guild.id})")  # Log join

    # Send welcome message
    embed = CustomEmbed(title=WELCOME_MESSAGE[0][0],
                        description=WELCOME_MESSAGE[0][1],
                        color=EMBED_COLOR)

    for line in WELCOME_MESSAGE[1:]:  # Dynamically add fields from configuration value
        embed.add_field(name=line[0], value=line[1])

    # Make an attempt at sending to the system channel, but don't crash if it doesn't exist
    try:
        await guild.system_channel.send(embed=embed)
    except AttributeError:
        f_log.info(ERROR_NO_SYSTEM_CHANNEL)


@client.event
async def on_guild_remove(guild: discord.Guild) -> None:
    """
    Purge data from guilds we were kicked from.
    TODO: implement
    :param guild: The guild we were removed from
    :return: nothing
    """
    f_log = log.getChild("event.guild_remove")
    f_log.info(f"Removed from guild {guild.name!r}! (id={guild.id}). that makes me sad :(")


async def presence() -> None:
    """
    Manage the presence of the bot.
    Rotates through presets and game names
    :return: None
    """
    presence_logger = logging.getLogger("playcord.presence")
    # Build presence options
    options = []
    for game in GAME_TYPES:
        info = GAME_TYPES[game]
        options.append(getattr(importlib.import_module(info[0]), info[1]).name)  # Add game's human readable name
    options.extend(["paper and pencil games", "fun", "distracting dervishes", "electrifying entertainment",
                    "gripping games"])  # Add presets
    while True:
        # Make a random activity
        activity = discord.Activity(type=discord.ActivityType.playing,
                                    name=random.choice(options) + " on Discord",
                                    state=f"Servicing {len(client.guilds)} servers and {len(client.users)} users")
        # Change presence
        try:
            await client.change_presence(activity=activity, status=discord.Status.online)
        except Exception as e:
            log.error(f"Failed to change presence status: {e!r} quitting presence until online again.")
            return
        # 15 seconds is the cooldown
        await asyncio.sleep(15)


async def matchmaking_button_callback(ctx: discord.Interaction) -> None:
    """
    Callback function for matchmaking.
    :param ctx: the interaction context
    :return: nothing
    """
    await ctx.response.defer()  # prevent interaction from failing

    f_log = log.getChild("callback.matchmaking_buttons")  # Get logger

    f_log.info(f"Matchmaking button for matchmaker {ctx.message.id} pressed! ID: {ctx.data['custom_id']}"
               f" context: {contextify(ctx)}")  # Log button press

    data = ctx.data['custom_id'].split("/")
    # Get a list of custom ID: <join/leave/start>/matchmaking_id

    # Extract data from data
    interaction_type: str = data[0]

    matchmaking_id: int = int(data[1])

    # Check if the game still exists
    if matchmaking_id in CURRENT_MATCHMAKING:
        matchmaker: MatchmakingInterface = CURRENT_MATCHMAKING[matchmaking_id]
    else:
        f_log.debug(f"Matchmaker expired when trying to press button (mode={interaction_type!r}): {contextify(ctx)}")
        await ctx.followup.send("This matchmaker has expired. Sorry about that :(", ephemeral=True)

        # Disable the buttons
        view = discord.ui.View.from_message(ctx.message)
        for button in view.children:
            button.disabled = True
        try:
            await ctx.message.edit(view=view, embed=ctx.message.embeds[0])
        except discord.HTTPException as http_exception:
            f_log.warning(f"Failed to disable matchmaker! This is likely fine: exc={str(http_exception)}"
                          f" {contextify(ctx)}")
        return

    if interaction_type == "join":
        await matchmaker.callback_ready_game(ctx=ctx)
    elif interaction_type == "leave":
        await matchmaker.callback_leave_game(ctx=ctx)
    elif interaction_type == "start":
        await matchmaker.callback_start_game(ctx=ctx)


async def game_button_callback(ctx: discord.Interaction, current_turn_required: bool = True) -> None:
    """
    Game button callback.
    :param ctx: discord button interaction
    :param current_turn_required: whether button can only be pressed if it is the player's turn
    :return: Nothing
    """
    await ctx.response.defer()  # Prevent button interaction from failing
    f_log = log.getChild("callback.game_button")  # Get logger

    f_log.info(f"Game button for game {ctx.channel.id} pressed! ID: {ctx.data['custom_id']}"
               f" context: {contextify(ctx)}")  # Log button press

    leading_str = "c/" if current_turn_required else "n/"  # Leading ID of custom ID string

    data: list[str] = ctx.data['custom_id'].replace(leading_str, "").split("/")
    # Get a list of custom ID: c/game_id/function_id/arguments

    # Extract data from data
    game_id: int = int(data[0])

    function_id: str = data[1]

    if data[2]:
        arguments = {arg.split("=")[0]: arg.split("=")[1] for arg in data[2].split(",")}
    else:  # No arguments
        arguments = {}

    # Check if the game still exists
    if game_id in CURRENT_GAMES:
        game_interface: GameInterface = CURRENT_GAMES[int(game_id)]
    else:
        f_log.debug(f"Game expired when trying to press button: {contextify(ctx)}")
        await ctx.followup.send("This game is over. Sorry about that :(", ephemeral=True)

        # Disable the buttons
        view = discord.ui.View.from_message(ctx.message)
        for button in view.children:
            button.disabled = True
        try:
            await ctx.message.edit(view=view, embed=ctx.message.embeds[0])
        except discord.HTTPException as e:
            f_log.warning(f"Failed to disable game! This is likely fine: exc={str(e)} {contextify(ctx)}")
        return

    # Call move_by_button callback
    await game_interface.move_by_button(ctx=ctx, name=function_id, arguments=arguments,
                                        current_turn_required=current_turn_required)


async def game_select_callback(ctx: discord.Interaction, current_turn_required: bool = True) -> None:
    """
    Game select menu callback.
    :param ctx: discord select interaction
    :param current_turn_required: whether select menu can only be interacted with if it is the player's turn
    :return: Nothing
    """
    await ctx.response.defer()  # Prevent interaction from failing
    f_log = log.getChild("callback.game_select")  # Get logger

    f_log.info(f"Game select menu for game {ctx.channel.id} pressed! ID: {ctx.data['custom_id']}"
               f" context: {contextify(ctx)}")  # Log button press

    leading_str = "select_c/" if current_turn_required else "select_n/"  # Leading ID of custom ID string

    data: list[str] = ctx.data['custom_id'].replace(leading_str, "").split("/")
    # Get a list of custom ID: select_[c/n]/game_id/function_id

    # Extract data from data
    game_id: int = int(data[0])

    function_id: str = data[1]

    # Check if the game still exists
    if game_id in CURRENT_GAMES:
        game_interface: GameInterface = CURRENT_GAMES[int(game_id)]
    else:
        f_log.debug(f"Game expired when trying to handle select menu: {contextify(ctx)}")
        await ctx.followup.send("This game is over. Sorry about that :(", ephemeral=True)

        # Disable the buttons
        view = discord.ui.View.from_message(ctx.message)
        for button in view.children:
            button.disabled = True
        try:
            await ctx.message.edit(view=view, embed=ctx.message.embeds[0])
        except discord.HTTPException as e:
            f_log.warning(f"Failed to disable game! This is likely fine: exc={str(e)} {contextify(ctx)}")
        return

    # Call move_by_select callback
    await game_interface.move_by_select(ctx=ctx, name=function_id,
                                        current_turn_required=current_turn_required)


async def invite_accept_callback(ctx: discord.Interaction) -> None:
    """
    Callback for clicking on invite buttons.
    Custom id is of the form invite/MATCHMAKERID

    :param ctx: discord context from button click
    :return: nothing
    """

    await ctx.response.defer()  # Prevent button interaction from failing

    # Log method activation
    f_log = log.getChild("callback.invite_accept")
    f_log.debug(f"invite-accept clicked: {contextify(ctx)}")

    # Get matchmaker ID
    matchmaker_id: str = ctx.data['custom_id'].replace('invite/', "")

    # If matchmaking is still happening, try to accept
    if int(matchmaker_id) in CURRENT_MATCHMAKING:
        matchmaker: MatchmakingInterface = CURRENT_MATCHMAKING[int(matchmaker_id)]
        error = await matchmaker.accept_invite(ctx)  # will return if invite accept failed
        if not error:
            await ctx.followup.send(
                "You have joined the game! Press 'Go To Game' to go to the server where the game is", ephemeral=True)
            f_log.debug(f"Invite successfully accepted: {contextify(ctx)}")
    else:  # Matchmaking is over or bot restarted
        await ctx.followup.send("This invite has expired.", ephemeral=True)
        f_log.debug(f"Invite expired: {contextify(ctx)}")

    # Disable invite button for click, regardless of success
    view = discord.ui.View.from_message(ctx.message)
    for button in view.children:
        if button.custom_id == "invite/" + matchmaker_id:
            button.disabled = True

    # Update invite embed
    await ctx.message.edit(view=view, embed=ctx.message.embeds[0])


async def spectate_callback(ctx: discord.Interaction) -> None:
    """
    Callback for clicking on spectate buttons.
    Custom ID format: spectate/GAMEID
    :param ctx: discord context
    :return: nothing
    """

    # Defer button interaction
    await ctx.response.defer()

    # Log that method was called
    f_log = log.getChild("callback.spectate")
    f_log.debug(f"spectate button clicked: {contextify(ctx)}")

    # Get game ID
    game_id: str = ctx.data['custom_id'].replace('spectate/', "")

    thread = client.get_channel(int(game_id))  # Try to get thread
    try:
        if thread is None:  # Thread doesn't exist
            thread = client.fetch_channel(int(game_id))  # Use API
        await thread.add_user(ctx.user)  # Add user to channel
        await ctx.followup.send("Successfully added user to game channel!", ephemeral=True)
    except discord.errors.NotFound:  # API said no lol
        await ctx.followup.send("That game no longer exists!", ephemeral=True)
        return


async def peek_callback(ctx: discord.Interaction) -> None:
    """
    Callback for peek buttons.
    Custom ID format: peek/GAMEID/MESSAGEID
    :param ctx: discord context
    :return: Nothing
    """
    await ctx.response.defer()  # Defer button interaction

    # Log that interaction was activated
    f_log = log.getChild("callback.peek")
    f_log.debug(f"peeked button clicked: {contextify(ctx)}")

    # Get data
    data = ctx.data['custom_id'].replace('peek/', "").split("/")

    # Unpack variables
    game_message_id: str = data[1]
    game_id: str = data[0]

    # Try to get thread from cache
    thread = client.get_channel(int(game_id))
    try:
        if thread is None:
            thread = client.get_channel(int(game_id))  # Use API if needed

        msg = await thread.fetch_message(int(game_message_id))  # Fetch message, unfortunately we need API

        # Get view from message to send back with disabled buttons
        message_view = discord.ui.View.from_message(msg)

        for button in message_view.children:  # don't want those buttons clickable lol
            button.disabled = True

        if len(msg.embeds):
            await ctx.followup.send(embed=msg.embeds[0], view=message_view, ephemeral=True)
        else:
            await ctx.followup.send(view=message_view, ephemeral=True)
    except discord.errors.NotFound:  # API takes the L
        await ctx.followup.send("That game no longer exists!", ephemeral=True)
        return


# Bot commands


@command_root.command(name="invite",
                      description="Invite a player to play a game, or remove them from the blacklist in public games.")
async def command_invite(ctx: discord.Interaction,
                         user: discord.User,
                         user2: discord.User = None,
                         user3: discord.User = None,
                         user4: discord.User = None,
                         user5: discord.User = None) -> None:
    """
    /invite: invites a user to a game.
    :param ctx: discord Context
    :param user: Player to invite to the game
    :param user2: Second player to invite to the game
    :param user3: Third player to invite to the game
    :param user4: Fourth player to invite to the game
    :param user5: Fifth player to invite to the game
    :return: Nothing, yet
    """

    f_log = log.getChild("command.invite")
    f_log.debug(f"/invite called: {contextify(ctx)}")  # Send context
    invited_users = {user, user2, user3, user4, user5}  # Condense to unique users
    if None in invited_users:
        invited_users.remove(None)

    id_matchmaking = {p.id: q for p, q in IN_MATCHMAKING.items()}  # get matchmaking by player ID

    if ctx.user.id not in id_matchmaking:  # Player isn't in matchmaking
        await ctx.response.send_message("You aren't in matchmaking, so you can't invite people to play.",
                                        ephemeral=True)  # TODO: invites start games
        f_log.debug(f"/invite rejected: not in matchmaking. {contextify(ctx)}")  # send context
        return

    matchmaker: MatchmakingInterface = id_matchmaking[ctx.user.id]  # Get the matchmaker for the game the player is in

    if matchmaker.private and matchmaker.creator.id != ctx.user.id:  # Only creators can invite in private games
        await ctx.response.send_message("You aren't the creator of this game, so you can't invite people to play.",
                                        ephemeral=True)
        f_log.debug(f"/invite rejected: not creator. {contextify(ctx)}")  # send context
        return

    game_type = matchmaker.game.name  # Get the human readable name of the game
    failed_invites = {}
    for invited_user in filter(None, invited_users):  # Filter out None values
        # Not in same server TODO: cross server matchmaking?
        if invited_user not in matchmaker.message.guild.members:
            failed_invites[invited_user] = "Member was not in server that the game was"
            continue
        # Member already in matchmaking
        if invited_user.id in [p.id for p in matchmaker.queued_players]:
            failed_invites[invited_user] = "Member was already in matchmaking."
            continue
        # Member already in game
        if invited_user in IN_GAME:
            failed_invites[invited_user] = "Member was already in a game."
            continue
        # Member is a bot
        if invited_user.bot:
            failed_invites[invited_user] = "Member was a bot :skull:."
            continue

        # Invitation TODO: custom embed class for invites that looks better
        embed = CustomEmbed(title=f"👋 Do you want to play a game?",
                            description=f"{ctx.user.mention} has invited you to play a game of {game_type}"
                                        f" in {matchmaker.message.guild.name!r}. If you don't want to play,"
                                        f" just ignore this message.")

        # Send embed and inviteview (note: invite ID is not game id, but actually the matchmaker's message id)
        await invited_user.send(embed=embed,
                                view=InviteView(join_button_id="invite/" + str(matchmaker.message.id),
                                                game_link=matchmaker.message.jump_url))
        continue

    # TODO: rework response to invites, I don't like how this is implemented
    if not len(failed_invites):
        f_log.debug(
            f"/invite success: {len(invited_users)} succeeded, 0 failed. {contextify(ctx)}")
        await ctx.response.send_message("Invites sent successfully.", ephemeral=True)
        return
    elif len(failed_invites) == len(invited_users):
        message = "Failed to send any invites. Errors:"
    else:
        message = "Failed to send invites to the following users:"
    f_log.debug(f"/invite partial or no success: {len(invited_users) - len(failed_invites)} succeeded,"
                f" {len(failed_invites)} failed. {contextify(ctx)}")
    final = message + "\n"
    for fail in failed_invites:
        final += f"{fail.mention} - {failed_invites[fail]}\n"
    await ctx.response.send_message(final, ephemeral=True)


@command_root.command(name="kick", description="Remove a user from your lobby without banning them.")
async def command_kick(ctx: discord.Interaction, user: discord.User, reason: str = None):
    """
    Kick the user from the lobby with a reason.

    :param ctx: discord context window
    :param user: user to kick
    :param reason: string representing reason
    :return: nothing
    """
    f_log = log.getChild("command.kick")
    id_matchmaking = {p.id: q for p, q in IN_MATCHMAKING.items()}

    if ctx.user.id not in id_matchmaking:
        f_log.debug(f"Failed to kick user: kicker not in matchmaking. {contextify(ctx)}")
        await ctx.response.send_message("You aren't in matchmaking, so you can't kick anyone.",
                                        ephemeral=True)
        return
    matchmaker: MatchmakingInterface = id_matchmaking[ctx.user.id]
    if matchmaker.creator.id != ctx.user.id:
        f_log.debug(f"Failed to kick user: not creator of game. {contextify(ctx)}")
        await ctx.response.send_message("You aren't the creator of this game, so you can't kick people from the game.",
                                        ephemeral=True)
        return

    return_value = await matchmaker.kick(user, reason)

    await ctx.response.send_message(return_value, ephemeral=True)


@command_root.command(name="ban", description="Either removes a user from the whitelist (private games)"
                                              "or adds them to the blacklist (public games)")
async def command_ban(ctx: discord.Interaction, user: discord.User, reason: str = None):
    f_log = log.getChild("command.ban")
    id_matchmaking = {p.id: q for p, q in IN_MATCHMAKING.items()}

    if ctx.user.id not in id_matchmaking:
        f_log.debug(f"Failed to ban user: banner not in matchmaking. {contextify(ctx)}")
        await ctx.response.send_message("You aren't in matchmaking, so you can't ban anyone.",
                                        ephemeral=True)
        return
    matchmaker: MatchmakingInterface = id_matchmaking[ctx.user.id]
    if matchmaker.creator.id != ctx.user.id:
        f_log.debug(f"Failed to ban user: attempted banner of creator. {contextify(ctx)}")
        await ctx.response.send_message("You aren't the creator of this game, so you can't ban people from the game.",
                                        ephemeral=True)
        return

    return_value = await matchmaker.ban(user, reason)

    await ctx.response.send_message(return_value, ephemeral=True)
    pass


@command_root.command(name="stats", description="Get stats about the bot")
async def command_stats(ctx: discord.Interaction):
    """
    Get stats for the bot.
    Metrics included:
    bot version
    d.py version
    Total guilds
    Total users
    Shard ID/Ping/Guilds
    Games Loaded
    # in matchmaking
    # in game
    :param ctx: discord Context
    :return: Nothing
    """
    f_log = log.getChild("command.stats")
    f_log.debug(f"/stats called: {contextify(ctx)}")  # Send context

    # Guild/user count
    server_count = len(client.guilds)
    member_count = len(set(client.get_all_members()))

    # Shard information
    shard_id = ctx.guild.shard_id
    shard_ping = client.latency
    shard_servers = len([guild for guild in client.guilds if guild.shard_id == shard_id])

    embed = CustomEmbed(title='PlayCord Stats <:pointing:1328138400808828969>', color=INFO_COLOR)

    # Row 1
    embed.add_field(name='💻 Bot Version:', value=VERSION)
    embed.add_field(name='🐍 discord.py Version:', value=discord.__version__)
    embed.add_field(name='🏘️ Total Servers:', value=server_count)

    # Row 2
    embed.add_field(name='<:user:1328138963512201256> Total Users:', value=member_count)
    embed.add_field(name='#️⃣ Shard ID:', value=shard_id)
    embed.add_field(name='🛜 Shard Ping:', value=str(round(shard_ping * 100, 2)) + " ms")

    # Row 3
    embed.add_field(name='🏘️️ Shard Guilds:', value=shard_servers)
    embed.add_field(name='👾 Games Loaded:', value=len(GAME_TYPES))
    embed.add_field(name="⏰ In Matchmaking:", value=len(IN_MATCHMAKING))

    # Row 4
    embed.add_field(name="🎮 In Game:", value=len(IN_GAME))

    await ctx.response.send_message(embed=embed)


@command_root.command(name="about", description="About the bot")
async def command_about(ctx: discord.Interaction):
    f_log = log.getChild("command.about")
    libraries = ["discord.py", "svg.py", "ruamel.yaml", "cairosvg", "trueskill", "mpmath"]
    f_log.debug(f"/about called: {contextify(ctx)}")  # Send context

    # Build about embed
    embed = CustomEmbed(title='About PlayCord 🎲', color=INFO_COLOR)
    embed.add_field(name="Bot by:", value="[@quantumbagel](https://github.com/quantumbagel)")
    embed.add_field(name="Source code:", value="[here](https://github.com/PlayCord/bot)")
    embed.add_field(name="PFP/Banner:", value="[@soldship](https://github.com/quantumsoldship)")
    embed.add_field(name="Inspiration:", value="[LoRiggio (Liar's Dice Bot)](https://github.com/Pixelz22/LoRiggioDev)"
                                               " by [@Pixelz22](https://github.com/Pixelz22)\n"
                                               "You know the drill, I had to beat Tyler :)", inline=True)
    embed.add_field(name="@USSyorktown10",
                    value="For this [awesome]"
                          "(https://github.com/PlayCord/bot/commit/9cb0262239be27b7bb04da5f1abc10c1990de3e7) commit.",
                    inline=False)
    embed.add_field(name="Libraries used:",
                    value="\n".join([f"[{lib}](https://pypi.org/project/{lib})" for lib in libraries]), inline=False)
    embed.add_field(name="Development time:", value="October 2024 - Present")
    embed.set_footer(text="©	2025 Julian Reder. All rights reserved. Except the 3rd.")

    # Send message back
    await ctx.response.send_message(embed=embed)


# Callbacks


async def begin_game(ctx: discord.Interaction, game_type: str, rated: bool = True, private: bool = False) -> None:
    """
    Begin a game
    :param ctx: Context from command callback function
    :param game_type: Game ID
    :param rated: is the game rated?
    :param private: is the game private?
    :return: Nothing
    """
    matchmaking_timer = Timer().start()
    f_log = log.getChild("command.matchmaking")  # Get logger
    f_log.debug(f"matchmaking called for game {game_type!r}: {contextify(ctx)}")  # Send context

    if not (ctx.channel.permissions_for(ctx.guild.me).create_private_threads
            and ctx.channel.permissions_for(ctx.guild.me).send_messages):  # Don't make the bot look stupid
        f_log.info(f"insufficient permissions triggered on matchmaking attempt for game {game_type!r}:"
                   f" {contextify(ctx)}")  # Send context
        await send_simple_embed(ctx, title="Insufficient Permissions",
                                description="Bot is missing permissions to function in this channel.", ephemeral=True)
        return

    # Can't begin a game because invalid channel type
    if ctx.channel.type == discord.ChannelType.public_thread or ctx.channel.type == discord.ChannelType.private_thread:
        # Send context
        f_log.info(f"invalid channel type triggered on matchmaking attempt for game {game_type!r}: {contextify(ctx)}")
        await send_simple_embed(ctx, title="Invalid Channel Type",
                                description="This command cannot be run in public or private threads.", ephemeral=True)

    # Start a "Loading" screen as we transition from matchmaking to GameOverviewEmbed
    await ctx.response.send_message(embed=CustomEmbed(description="<a:loading:1318216218116620348>").remove_footer())
    game_overview_message = await ctx.original_response()

    # Create MatchmakingInterface
    interface = MatchmakingInterface(ctx.user, game_type, game_overview_message, rated=rated, private=private)

    if interface.failed is not None:  # Interface failed to start, edit overview message with crash
        await game_overview_message.edit(embed=interface.failed)
        return

    await interface.update_embed()  # Update embeds (first paint)
    f_log.debug(f"Finished matchmaking initialization in {matchmaking_timer.stop()}ms. game_type={game_type!r}"
                f" ctx={contextify(ctx)}")


async def handle_move(ctx: discord.Interaction, name, arguments) -> None:
    """
    Handle move (dynamically) from discord arguments
    :param ctx: discord context
    :param name: Name of the move command
    :param arguments: Arguments passed to the move command
    :return: nothing
    """

    f_log = log.getChild("callback.handle_move")
    # Must be run in private thread
    if ctx.channel.type != discord.ChannelType.private_thread:
        f_log.info(f"invalid channel type triggered on handling move {contextify(ctx)}")
        await send_simple_embed(ctx, "Move commands can only be run in their respective threads",
                                "Please use a bot-created thread to move. :) ", responded=True)
        return
    # Must be in current game
    if ctx.channel.id not in CURRENT_GAMES.keys():
        f_log.info(f"invalid channel (not a game channel) triggered on handling move {contextify(ctx)}")
        await send_simple_embed(ctx, "Move commands can only be run in a channel where there is a game.",
                                "Please start a game to use this command :)", responded=True)
        return

    # Don't pass ctx to internals
    arguments.pop("ctx")
    # Decode arguments from discord.py provided internals to parsable python types
    arguments = {a: await decode_discord_arguments(arguments[a]) for a in arguments.keys()}

    AUTOCOMPLETE_CACHE[ctx.channel.id] = {}  # Reset autocomplete cache for this game

    # Call GameInterface move callback with arguments
    await CURRENT_GAMES[ctx.channel.id].move_by_command(ctx, name, arguments)  # TODO: add current_turn_required


async def handle_autocomplete(ctx: discord.Interaction, function, current: str, argument) -> list[Choice[str]]:
    """
    Crappy autocomplete. TODO: make this algorithm better at predicting
    :param function:
    :param ctx: discord context
    :param current: the current typed argument (like "do" for someone typing "dog")
    :param argument: Which argument we are completing
    :return: A list of Choices representing the possibilities
    """

    # Get the current game
    logger = log.getChild("callback.handle_autocomplete")
    try:
        # Try to get the GameInterface object
        game_view = CURRENT_GAMES[ctx.channel.id]
    except KeyError:  # Game not in this channel
        logger.info(f"There is no game from channel #{ctx.channel.mention} (id={ctx.channel.id}). Not autocompleting."
                    f" context: {contextify(ctx)}")

        # Use the autocomplete choices as a cheese to inform user
        return [app_commands.Choice(name="There is no game in this channel!", value="")]

    # Get the player who called this function from database
    player = database.get_player(game_view.game_type, ctx.user)
    try:
        # attempt to retrieve data from autocomplete cache
        player_options = AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id][function][argument][current]
        logger.info(f"Successfully used autocomplete cache:"
                    f" function={function} argument={argument}, current={current!r} context: {contextify(ctx)}")
    except KeyError:
        ac_callback = None
        # Get the autocomplete callback function for this argument
        # This MUST exist because this function was called
        for move in game_view.game.moves:
            for option in move.options:
                if option.name == argument:
                    ac_callback = getattr(game_view.game, option.autocomplete)
                    break

        # Force reload: save autocomplete cache data.
        if not option.force_reload:  # If we can save data, do that
            try:
                # Get the options for the player from the backend
                player_options = ac_callback(player)

                # Collection of if statements to make sure correct structure is built, not sure of a better way lol
                if ctx.channel.id not in AUTOCOMPLETE_CACHE:
                    AUTOCOMPLETE_CACHE[ctx.channel.id] = {}

                if ctx.user.id not in AUTOCOMPLETE_CACHE[ctx.channel.id]:
                    AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id] = {}

                if function not in AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id]:
                    AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id][function] = {}

                if argument not in AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id][function]:
                    AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id][function][argument] = {}

                # Actually save data to autocomplete cache
                AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id][function][argument].update({current: player_options})
            except TypeError:
                logger.critical(f"handle_autocomplete was called without a matching callback function."
                                f" function={function} argument={argument},"
                                f" options={game_view.game.options}, current={current!r} context: {contextify(ctx)}")
                return [app_commands.Choice(name="Autocomplete function is not defined!", value="")]

        else:
            # No autocomplete cache
            logger.info(f"force_reload blocked autocomplete cache function={function} argument={argument},"
                        f" options={game_view.game.options}, current={current!r} {contextify(ctx)}")

            try:
                player_options = ac_callback(player)  # try to get autocomplete data
            except TypeError:
                logger.critical(f"handle_autocomplete was called without a matching callback function."
                                f" function={function} argument={argument},"
                                f" options={game_view.game.options}, current={current!r} context: {contextify(ctx)}")
                return [app_commands.Choice(name="Autocomplete function is not defined!", value="")]

    # Get all valid options based on what is currently typed (e.g. only allow words containing "amo" for a typed "amo"
    valid_player_options = []
    for option in player_options:
        name = next(iter(option))
        if current.lower() in name.lower():
            valid_player_options.append([name, option[name]])

    # Sort based on how early the string is
    # i.e. DOg > hairDO for string "do"
    final_autocomplete = sorted(valid_player_options, key=lambda x: x[0].lower().index(current.lower()))

    return [app_commands.Choice(name=ac_option[0], value=ac_option[1])  # Return as Choices instead of list of lists
            for ac_option in final_autocomplete]


# Dynamic function generation


async def decode_discord_arguments(argument: Choice | typing.Any) -> typing.Any:
    """
    Decode discord arguments from discord so they can be passed to the move function
    Currently implemented: app_commands.Choice

    User move command -> Parser -> **decode_discord_arguments** -> GameInterface -> internal Game move function
    :param argument: the argument
    :return: the decoded argument
    """
    if isinstance(argument, Choice):  # Choice should just return its value
        return argument.value
    else:  # Just return the argument
        return argument


def encode_argument(argument_name, argument_information) -> str:
    """
    Encode an argument into the form
    arg:str{=None}

    :param argument_name: The name of the argument to encode
    :param argument_information: Information about the argument (type and whether it is option)
    :return: the encoded argument
    """
    if argument_information["type"].__class__ is RangeTransformer:  # Special case
        # Extract the type and min/max values
        option_type = argument_information["type"]._type
        if option_type == AppCommandOptionType.integer:
            range_type = int
        elif option_type == AppCommandOptionType.string:
            range_type = str

        # Extract min/max
        min_value, max_value = argument_information["type"]._min, argument_information["type"]._max

        # Format as string
        argument_type = f"app_commands.Range[{range_type.__name__}, {min_value}, {max_value}]"
    else:
        argument_type = argument_information["type"].__name__  # Get string of type ("str")
    # Make the argument optional if required
    optional_addendum = ''
    if argument_information["optional"]:
        optional_addendum = '=None'

    # hi:str=None or hi:str
    return f"{argument_name}:{argument_type}{optional_addendum}"


def encode_decorator(decorator_type, decorator_values) -> str:
    """
    Encode a decorator into the form
    @app_commands.dec_name(arg=value, arg2=value2)

    :param decorator_type: the decorator type (dec_name)
    :param decorator_values: a dictionary of the decorators ({arg: value, arg2: value2})
    :return: the encoded decorator as a string
    """
    stringified_arguments = []

    # Get a list like ["arg=value", "arg2=value2"]
    for command_argument in decorator_values:
        stringified_arguments.append(f"{command_argument}={str(decorator_values[command_argument])}")
    function_arguments = ','.join(stringified_arguments)  # "arg=value,arg2=value

    return f"@app_commands.{decorator_type}({function_arguments})"  # Put it all together


def build_function_definitions() -> dict[Group, list[Any]]:
    """
    Build the dynamic functions

    This includes:
    move commands
    autocomplete callbacks

    :return: a list of strings each representing a function that needs to be added to the global
    """
    context = {play: []}  # Play group is for the game's start function
    for game in GAME_TYPES:  # for each registered game
        # Import the game's module
        game_class = getattr(importlib.import_module(GAME_TYPES[game][0]), GAME_TYPES[game][1])  # Get the game's class

        # Register game begin function
        game_command = (f"@group.command(name={game!r}, description={game_class.begin_command_description!r})\n"
                        f"async def begin_{game}(ctx: discord.Interaction, rated: bool = True, private: bool = False):\n"
                        f"  await begin_game(ctx, {game!r}, rated=rated, private=private)")

        context[play].append(game_command)  # Add game context

        moves: list[Command] = game_class.moves  # Get the game's defined move option set

        # Decorators and arguments to build from
        decorators = {}  # {move_name: }
        arguments = {}

        for move in moves:

            # Decorators and arguments for just the move
            temp_decorators = {}
            temp_arguments = {}
            if move.options is None:  # No options
                # Save empty dicts to the values so nothing is saved
                decorators[move.name] = temp_decorators
                arguments[move.name] = temp_arguments
                continue
            for option in move.options:
                # Obtain the decorators and arguments that the option uses
                option_decorators = option.decorators()

                # Autocomplete check
                if "autocomplete" not in option_decorators and option.autocomplete is not None:
                    option_decorators.update({"autocomplete":
                                                  {option.name: "autocomplete_" + option.autocomplete}})

                option_arguments = option.arguments()  # Get the arguments from the option

                # Add each argument
                for argument in option_arguments:
                    temp_arguments.update({argument: option_arguments[argument]})

                # Add each decorator, but some extra logic for stacking multiple variables of same decorator type
                for decorator in option_decorators.keys():
                    if decorator not in decorators.keys():
                        temp_decorators[decorator] = option_decorators[decorator]
                    else:
                        temp_decorators[decorator].update({decorator: option_decorators[decorator]})

            # Set decorators and arguments for the move
            decorators[move.name] = temp_decorators
            arguments[move.name] = temp_arguments

        for this_move in moves:
            # Encode decorators to text
            encoded_decorators = []

            # Get the decorators and arguments
            this_move_decorators = decorators[this_move.name]
            this_move_arguments = arguments[this_move.name]

            # Command group for this game's move commands
            dynamic_command_group = app_commands.Group(name=game, description=game_class.move_command_group_description)
            context[dynamic_command_group] = []

            # Encode decorators to text
            for unencoded_decorator in this_move_decorators:
                encoded_decorators.append(
                    encode_decorator(unencoded_decorator, this_move_decorators[unencoded_decorator]))

            # Encode arguments to text
            encoded_arguments = []
            for unencoded_argument in this_move_arguments:
                encoded_arguments.append(
                    encode_argument(unencoded_argument, this_move_arguments[unencoded_argument]))

            command_name = game + "_" + this_move.name  # Name of move command to register (e.g. tictactoe_move)

            # Build the move command
            move_command = (f"{'\n'.join(encoded_decorators)}\n"
                            f"@group.command(name='{this_move.name}', description='{this_move.description}')\n"
                            f"async def {command_name}(ctx, {','.join(encoded_arguments)}):\n"
                            f"  await ctx.response.defer(ephemeral=True)\n"
                            f"  await handle_move(ctx=ctx, name={this_move.name!r}, arguments=locals())\n")

            if "autocomplete" in this_move_decorators.keys():  # If there is any autocomplete support for this command
                for autocomplete in this_move_decorators["autocomplete"]:
                    # Name of autocomplete command
                    ac_command_name = this_move_decorators["autocomplete"][autocomplete]

                    # Actual autocomplete command
                    ac_command = (f"async def {ac_command_name}(ctx, current):\n"
                                  f"   return await handle_autocomplete(ctx, {this_move.name!r}, current, {autocomplete!r})\n")

                    # Add the autocomplete command
                    context[dynamic_command_group].append(ac_command)

            # Add the move command, so autocomplete callbacks are built before the move command
            context[dynamic_command_group].append(move_command)

    return context


# Mainloop

if __name__ == "__main__":
    try:
        commands = build_function_definitions()  # Build game move callbacks
        startup_logger.info(f"Built command hooks for {len(commands)} groups (games)"
                            f" and {sum([len(commands[g]) for g in commands])} callbacks (autocomplete and move commands).")
        # Register commands
        for group in commands:
            tree.add_command(group)
            for command in commands[group]:
                startup_logger.debug(f"Registering command:\n{command}")
                exec(command)  # Add the command

        startup_logger.info(f"All hooks registered.")


    except Exception as e:
        # Error on startup
        startup_logger.critical(str(e))
        startup_logger.critical("Error building and registering bot commands!")
        raise e
    try:

        # Add command groups to tree
        tree.add_command(command_root)

        # Run the bot :)
        startup_logger.info(f"Starting client after {round((time.time() - startup_initial_time) * 100, 4)}ms")
        client.run(config[CONFIG_BOT_SECRET], log_handler=None)
    except Exception as e:  # Something went wrong
        log.critical(str(e))
        log.critical(ERROR_INCORRECT_SETUP)
