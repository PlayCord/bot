import importlib
import logging
import sys

import discord
import trueskill
from discord import app_commands, ChannelType, Member, User
from discord.app_commands import Choice
import utils.logging_formatter
from configuration.constants import *
import configuration.constants as constants
from ruamel.yaml import YAML

from utils import Database
from utils.CustomEmbed import CustomEmbed
from utils.Database import get_player
from utils.GameInterface import GameInterface, MatchmakingInterface, MatchmakingView
from utils.InputTypes import Dropdown, InputType
import typing




logging.getLogger("discord").setLevel(logging.INFO)  # Discord.py logging level - INFO (don't want DEBUG)

logging.basicConfig(level=logging.DEBUG)

# Configure root logger
root_logger = logging.getLogger("root")
root_logger.setLevel(logging.DEBUG)

# create console handler with a higher log level
ch = logging.StreamHandler(stream=sys.stdout)
ch.setLevel(logging.DEBUG)

ch.setFormatter(utils.logging_formatter.Formatter())  # custom formatter
root_logger.handlers = [ch]  # Make sure to not double print

log = logging.getLogger(LOGGING_ROOT)  # Base logger
if __name__ != "__main__":
    log.critical(ERROR_IMPORTED)
    sys.exit(1)


def load_configuration() -> dict:
    """
    Load configuration from constants.CONFIG_FILE
    :return: the configuration as a dictionary
    """
    try:
        loaded_config_file = YAML().load(open(CONFIG_FILE))
    except FileNotFoundError:
        log.critical("Configuration file not found.")
        return None
    log.debug("Successfully loaded configuration file!")
    return loaded_config_file

config = load_configuration()
constants.CONFIGURATION = config  # Set global configuration

database_startup = Database.startup()  # Start up the database
if not database_startup:  # Database better work lol
    log.critical("Database failed to connect on startup!")
    sys.exit(1)



client = discord.Client(intents=discord.Intents.all())  # Create the client with all intents, so we can read messages
tree = app_commands.CommandTree(client)  # Build command tree



# Root command registration
command_root = app_commands.Group(name=LOGGING_ROOT, description="PlayCord command group. ChangeME", guild_only=True)


log.info(f"Welcome to {NAME} by @quantumbagel!")





def simple_embed(title: str, description: str) -> CustomEmbed:
    """
    Generate a simple embed
    :param title: the title
    :param description: the description
    :return: the embed
    """
    embed = CustomEmbed(title=title, description=description)
    return embed


async def send_simple_embed(ctx: discord.Interaction, title: str, description: str, ephemeral: bool = True,
                            responded: bool = False) -> None:
    """
    Generate a simple embed
    :param title: the title
    :param description: the description
    :return: the embed
    """
    if not responded:
        await ctx.response.send_message(embed=simple_embed(title, description), ephemeral=ephemeral)
    else:
        # Use the followup for sending the embed simply because ctx.response won't work
        await ctx.followup.send(embed=simple_embed(title, description), ephemeral=ephemeral)


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


    if not IS_ACTIVE:  # Bot disabled via mesage command
        await send_simple_embed(ctx, "Bot has been disabled!", f"{NAME} "
                                      f"has been temporarily disabled by a bot owner. This"
                                      " is likely due to a critical bug or exploit being discovered.")
        return False

    if ctx.user.bot:  # We don't want no bots
        logger.warning("Bot users are not allowed to use commands.")
        return False

    if str(ctx.channel.type) == "private":  # No DMs - maybe in the future?
        logger.error("Commands don't work in DMs!")
        await send_simple_embed(ctx, "Commands don't work in DMs!",
                                      f"{NAME} is a server-only bot currently. requires a server for its commands to work."
                                      " Support for some DM commands may come in the future.")
        return False

    return True


command_root.interaction_check = interaction_check  # Set the interaction check


@client.event
async def on_ready():
    # Register views to the bot
    client.add_view(MatchmakingView())

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
    if msg.content.startswith(f"{LOGGING_ROOT}/{MESSAGE_COMMAND_SYNC}") and msg.author.id in OWNERS:  # Perform sync
        split = msg.content.split()
        if len(split) == 1:
            await tree.sync()
            f_log.info(f"Performed authorized sync from user {msg.author.id} to all guilds.")
        else:
            if split[1] == MESSAGE_COMMAND_SPECIFY_LOCAL_SERVER:
                g = msg.guild
            else:
                try:
                    g = discord.Object(id=int(split[1]))
                except ValueError:
                    return
            tree.copy_global_to(guild=g)
            await tree.sync(guild=g)
            f_log.info(f"Performed authorized sync from user {msg.author.id} to guild \"{g.name}\" (id=\"{g.id}\")")
        await msg.add_reaction(MESSAGE_COMMAND_SUCCEEDED)  # leave confirmation
        return

    # Disable
    elif msg.content == f"{LOGGING_ROOT}/{MESSAGE_COMMAND_DISABLE}" and msg.author.id in OWNERS:  # Disable bot
        if not IS_ACTIVE:
            await msg.add_reaction(MESSAGE_COMMAND_FAILED)  # Don't need to disable
            return
        IS_ACTIVE = False
        f_log.critical(f"Bot has been disabled by authorized user {msg.author.id}.")

        await msg.add_reaction(MESSAGE_COMMAND_FAILED)  # leave confirmation
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
            await msg.add_reaction(MESSAGE_COMMAND_FAILED)
        return

    # Clear command tree
    elif msg.content == f"{LOGGING_ROOT}/{MESSAGE_COMMAND_CLEAR}" and msg.author.id in OWNERS:
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
            tree.clear_commands(guild=g)
            tree.copy_global_to(guild=g)
            await tree.sync(guild=g)
            f_log.info(f"Performed authorized command tree clear from user {msg.author.id} "
                       f"to guild \"{g.name}\" (id=\"{g.id}\")")
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
    f_log.info("Added to guild \"" + guild.name + f"\"! (id={guild.id})")  # Log join

    # Send welcome message
    embed = CustomEmbed(title=WELCOME_MESSAGE[0][0],
                          description=WELCOME_MESSAGE[0][1],
                          color=EMBED_COLOR)


    for line in WELCOME_MESSAGE[1:]:  # Dynamically add fields from configuration value
        embed.add_field(name=line[0], value=line[1])

    # Make a attempt at sending to the system channel, but don't crash if it doesn't exist
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
    pass

@command_root.command(name="invite", description="Invite a player to play the game you're queued for")
async def command_invite(ctx: discord.Interaction,
                         user: discord.User,
                         user2: discord.User = None,
                         user3: discord.User = None,
                         user4: discord.User = None,
                         user5: discord.User = None) -> None:
    invited_users = {user, user2, user3, user4, user5}
    for invited_user in filter(None, invited_users):  # Filter out None values
        continue
    await ctx.response.send_message("Invites sent successfully.", ephemeral=True)
    

@command_root.command(name="tictactoe", description="Tic-Tac Toe is a game about replacing your toes with Tic-Tacs,"                                                    " obviously.")
async def tictactoe(ctx: discord.Interaction, rated: bool = True):


    if not (ctx.channel.permissions_for(ctx.guild.me).create_private_threads
            and ctx.channel.permissions_for(ctx.guild.me).send_messages):  # Don't make the bot look stupid
        await send_simple_embed(ctx, title="Insufficient Permissions", description="Bot is missing permissions to function in this channel.")
        return

    await send_simple_embed(ctx, title="Loading game...", description="This should take less than a second. PlayCord is setting up everything behind the scenes.", ephemeral=False)
    thing = await ctx.original_response()


    g = MatchmakingInterface(ctx.user, "tic_tac_toe", thing, rated=rated)

    if g.failed is not None:
        await thing.edit(embed=g.failed)
        return

    await g.update_embed()


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


async def handle_move(ctx: discord.Interaction, **arguments):
    if ctx.channel.type != discord.ChannelType.private_thread:
        await send_simple_embed(ctx, "Move commands can only be run in their respective threads",
                                "Please use a bot-created thread to move. :)", responded=True)
        return
    if ctx.channel.id not in CURRENT_GAMES.keys():
        await send_simple_embed(ctx, "Move commands can only be run in their respective threads",
                                "Please use a bot-created thread to move. :)", responded=True)
        return
    pass_through_arguments: dict = arguments["arguments"]
    pass_through_arguments.pop("ctx")
    pass_through_arguments = {a: await decode_discord_arguments(pass_through_arguments[a]) for a in pass_through_arguments.keys()}



    AUTOCOMPLETE_CACHE[ctx.channel.id] = {}  # Reset autocomplete cache
    await CURRENT_GAMES[ctx.channel.id].move(ctx, pass_through_arguments)


async def handle_autocomplete(ctx: discord.Interaction, current: str, argument) -> list[Choice[str]]:
    """
    Crappy autocomplete. TODO: make this algorithm better at predicting
    :param ctx: discord context
    :param current: the current typed argument (like "do" for someone typing "dog")
    :param argument: Which argument we are completing
    :return: A list of Choices representing the possibilities
    """

    # Get the current game
    logger = log.getChild("autocomplete")
    try:
        game_view = CURRENT_GAMES[ctx.channel.id]
    except KeyError:  # Game not in this channel
        logger.info(f"There is no game from channel #{ctx.channel.mention} (id={ctx.channel.id}). Not autocompleting.")
        return [app_commands.Choice(name="There is no game in this channel!", value="")]

    player = get_player(game_view.game_type, ctx.user)  # Get the player who called this function
    try:
        player_options = AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id][argument][current]
        logger.info(f"Successfully used autocomplete cache: channel_id={ctx.channel.id}, user_id={ctx.user.id}, argument={argument}, current=\"{current}\"")
    except KeyError:
        ac_callback = None
        for option in game_view.game.options:
            if option.name == argument:
                # Get the autocomplete callback for this argument
                # This MUST exist because this function was called
                ac_callback = getattr(game_view.game, option.autocomplete)

        if not option.force_reload:
            try:
                # Get the options for the player from the backend
                player_options = ac_callback(player)
                if ctx.channel.id not in AUTOCOMPLETE_CACHE:
                    AUTOCOMPLETE_CACHE[ctx.channel.id] = {}
                if ctx.user.id not in AUTOCOMPLETE_CACHE[ctx.channel.id]:
                    AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id] = {}
                if argument not in AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id]:
                    AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id][argument] = {}
                AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id][argument].update({current: player_options})
            except TypeError:
                logger.critical(f"handle_autocomplete was called without a matching callback function."
                                f" channel_id={ctx.channel.id}, user_id={ctx.user.id}, argument={argument},"
                                f" options={game_view.game.options}, current=\"{current}\"")
        else:
            logger.info("force_reload blocked autocomplete cache")

    # Get all valid options
    valid_player_options = []
    for option in player_options:
        name = next(iter(option))
        if current.lower() in name.lower():
            valid_player_options.append([name, option[name]])

    # Sort based on how early the string is
    # i.e. DOg > hairDO for string "do"
    final_autocomplete = sorted(valid_player_options, key=lambda x: x[0].lower().index(current.lower()))


    return [app_commands.Choice(name=ac_option[0],value=ac_option[1])  # Return as Choices instead of list of lists
            for ac_option in final_autocomplete]


# Group for all move commands TODO: rework for less confusing? is this fine?
move_group = app_commands.Group(name="move", description="Move controls")
move_group.interaction_check = interaction_check  # Set interaction check as well for this group


def encode_argument(argument_name, argument_information) -> str:
    """
    Encode an argument into the form
    arg:str{=None}

    :param argument_name: The name of the argument to encode
    :param argument_information: Information about the argument (type and whether it is option)
    :return: the encoded argument
    """
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
    function_arguments = ','.join(stringified_arguments) # "arg=value,arg2=value

    return f"@app_commands.{decorator_type}({function_arguments})"  # Put it all together


def build_function_definitions() -> list[str]:
    """
    Build the dynamic functions

    This includes:
    move commands
    autocomplete callbacks

    :return: a list of strings each representing a function that needs to be added to the global
    """
    context = []
    for game in GAME_TYPES:  # for each registered game
        # Import the game's module
        game_class = getattr(importlib.import_module(GAME_TYPES[game][0]), GAME_TYPES[game][1])  # Get the game's class
        options: list[InputType] = game_class.options  # Get the game's defined move option set

        # Decorators and arguments to build from
        decorators = {}
        arguments = {}

        for option in options:
            # Obtain the decorators and arguments that the option uses
            option_decorators = option.decorators()

            # Autocomplete check
            if "autocomplete" not in option_decorators and option.autocomplete is not None:
                option_decorators.update({"autocomplete": {option.name: "autocomplete_"+option.autocomplete}})

            option_arguments = option.arguments()  # Get the arguments

            # Add each argument
            for argument in option_arguments:
                arguments.update({argument: option_arguments[argument]})

            # Add each decorator, but some extra logic for stacking multiple variables of same decorator type
            for decorator in option_decorators.keys():
                if decorator not in decorators.keys():
                    decorators[decorator] = option_decorators[decorator]
                else:
                    decorators[decorator].update({decorator: option_decorators[decorator]})

        # Encode decorators to text
        encoded_decorators = []
        for unencoded_decorator in decorators:
            encoded_decorators.append(encode_decorator(unencoded_decorator, decorators[unencoded_decorator]))

        # Encode arguments to text
        encoded_arguments = []
        for unencoded_argument in arguments:
            encoded_arguments.append(encode_argument(unencoded_argument, arguments[unencoded_argument]))

        command_name = game+"_move"  # Name of move command to register


        # Build the move command
        move_command = (f"{'\n'.join(encoded_decorators)}\n"
                        f"@move_group.command(name='{game}', description='{game_class.command_description}')\n"
                        f"async def {command_name}(ctx, {','.join(encoded_arguments)}):\n"
                        f"  await ctx.response.defer(ephemeral=True)\n"
                        f"  await handle_move(ctx=ctx, arguments=locals())\n")

        if "autocomplete" in decorators.keys():  # If there is any autocomplete support for this command
            for autocomplete in decorators["autocomplete"]:

                # Name of autocomplete command
                ac_command_name = decorators["autocomplete"][autocomplete]

                # Actual autocomplete command
                ac_command = (f"async def {ac_command_name}(ctx, current):\n"
                              f"   return await handle_autocomplete(ctx, current, \"{autocomplete}\")\n")

                # Add the autocomplete command
                context.append(ac_command)

        # Add the move command, so autocomplete callbacks are built before the move command
        context.append(move_command)

    return context


if __name__ == "__main__":
    try:
        commands = build_function_definitions()  # Build game move callbacks
        log.info(f"Built {len(commands)} hooks.")
        # Register commands
        for command in commands:
            exec(command)  # Add the command

        log.info(f"Hooks registered.")


    except Exception as e:
        log.critical(str(e))
        log.critical("Error registering bot commands!")
        sys.exit(1)  # Exit here
    try:

        # Add command groups to tree
        tree.add_command(command_root)
        tree.add_command(move_group)

        # Run the bot :)
        client.run(config[CONFIG_BOT_SECRET], log_handler=None)
    except Exception as e:  # Something went wrong
        log.critical(str(e))
        log.critical(ERROR_INCORRECT_SETUP)