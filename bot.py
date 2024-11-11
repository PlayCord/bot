# PlayCord
import importlib
import logging
import sys

import discord
from discord import app_commands, ChannelType, Member, User
from discord.app_commands import Choice
import utils.logging_formatter
from configuration.constants import *
import configuration.constants as constants
from ruamel.yaml import YAML

from utils import Database
from utils.CustomEmbed import CustomEmbed
from utils.Database import get_player
from utils.GameView import GameView, MatchmakingView
from utils.InputTypes import Dropdown, InputType

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





def load_configuration():
    """
    Load configuration from constants.CONFIG_FILE
    :return:
    """
    try:
        loaded_config_file = YAML().load(open(CONFIG_FILE))
    except FileNotFoundError:
        log.critical("Configuration file not found.")
        return None
    log.debug("Successfully loaded configuration file!")
    return loaded_config_file

config = load_configuration()
constants.CONFIGURATION = config

IS_ACTIVE = True  # Use to keep track of whether the bot is alive TODO: move to constants

database_startup = Database.startup()
if not database_startup:
    log.critical("Database failed to connect on startup!")
    sys.exit(1)



client = discord.Client(intents=discord.Intents.all())
tree = app_commands.CommandTree(client)  # Build command tree



# Root command registration
command_root = app_commands.Group(name=LOGGING_ROOT, description="The heart and soul of the game.", guild_only=True)


# I don't think that description is visible anywhere, but maybe it is lol.
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
                            responded: bool = False):
    """
    Generate a simple embed
    :param title: the title
    :param description: the description
    :return: the embed
    """
    if not responded:
        await ctx.response.send_message(embed=simple_embed(title, description), ephemeral=ephemeral)
    else:
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


    if not IS_ACTIVE:
        await send_simple_embed(ctx, "Bot has been disabled!", f"{NAME} "
                                      f"has been temporarily disabled by a bot owner. This"
                                      " is likely due to a critical bug or exploit being discovered.")
        return False
    if ctx.user.bot:
        logger.warning("Bot users are not allowed to use commands.")
        return False
    if str(ctx.channel.type) == "private":  # No DMs - yet
        logger.error("Commands don't work in DMs!")
        await send_simple_embed(ctx, "Commands don't work in DMs!",
                                      f"{NAME} is a server-only bot currently. requires a server for its commands to work."
                                      " Support for some DM commands may come in the future.")
        return False

    return True

command_root.interaction_check = interaction_check


@client.event
async def on_message(msg: discord.Message) -> None:
    """
    Handle message commands
    :param msg: The message
    :return: None
    """
    global IS_ACTIVE
    f_log = log.getChild("event.on_message")
    # Message synchronization command
    print(msg.channel.id, CURRENT_THREADS)
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
    f_log.info("Added to guild \"" + guild.name + f"\"! (id={guild.id})")
    embed = CustomEmbed(title=WELCOME_MESSAGE[0][0],
                          description=WELCOME_MESSAGE[0][1],
                          color=EMBED_COLOR)
    for line in WELCOME_MESSAGE[1:]:
        embed.add_field(name=line[0], value=line[1])

    try:
        await guild.system_channel.send(embed=embed)
    except AttributeError:
        f_log.info(ERROR_NO_SYSTEM_CHANNEL)


@client.event
async def on_guild_remove(guild: discord.Guild) -> None:
    """
    Purge data from guilds we were kicked from.
    :param guild: The guild we were removed from
    :return: nothing
    """
    f_log = log.getChild("event.guild_remove")

    pass



@command_root.command(name="tictactoe", description="Tic-Tac Toe is a game about replacing your toes with Tic-Tacs,"
                                                    " obviously.")
async def tictactoe(ctx: discord.Interaction):
    #await ctx.response.defer()
    #message = ctx.followup

    if not (ctx.channel.permissions_for(ctx.guild.me).create_private_threads
            and ctx.channel.permissions_for(ctx.guild.me).send_messages):
        await send_simple_embed(ctx, title="Insufficient Permissions", description="Bot is missing permissions to function in this channel.")
        return
    await send_simple_embed(ctx, title="Loading game...", description="This should take less than a second. PlayCord is setting up everything behind the scenes.", ephemeral=False)
    thing = await ctx.original_response()

    g = MatchmakingView(ctx.user, "tic_tac_toe", thing, rated=True)

    if g.failed is not None:
        await thing.edit(embed=g.failed)
        return

    await g.update_embed()

async def decode_discord_arguments(argument):
    if isinstance(argument, Choice):
        return argument.value
    if isinstance(argument, User):
        return get_player(argument.id)
    else:
        return argument



async def handle(ctx: discord.Interaction, **arguments):
    if ctx.channel.type != discord.ChannelType.private_thread:
        await send_simple_embed(ctx, "Move commands can only be run in their respective threads",
                                "Please use a bot-created thread to move. :)", responded=True)
        return
    if ctx.channel.id not in CURRENT_THREADS.keys():
        await send_simple_embed(ctx, "Move commands can only be run in their respective threads",
                                "Please use a bot-created thread to move. :)", responded=True)
        return
    print("outer", arguments)
    pass_through_arguments: dict = arguments["arguments"]
    pass_through_arguments.pop("ctx")
    pass_through_arguments = {a: await decode_discord_arguments(pass_through_arguments[a]) for a in pass_through_arguments.keys()}
    await CURRENT_GAMES[CURRENT_THREADS[ctx.channel.id]].move(pass_through_arguments)
    await ctx.followup.send(content="Moved", ephemeral=True, delete_after=5)

async def handle_autocomplete(ctx: discord.Interaction, current: str, argument):
    game_view = CURRENT_GAMES[CURRENT_THREADS[ctx.channel.id]]
    player = get_player(game_view.game_type, ctx.user)

    ac_callback = None
    for option in game_view.game.options:
        if option.name == argument:
            ac_callback = getattr(game_view.game, option.autocomplete)

    things = ac_callback(player)



    return [app_commands.Choice(name=next(iter(ac_option)),value=ac_option[next(iter(ac_option))]) for ac_option in things]





move_group = app_commands.Group(name="move", description="Move controls")
move_group.interaction_check = interaction_check

def encode_argument(argument_name, argument_information):
    argument_type = argument_information["type"]
    optional_addendum = ''

    # Make the argument optional if required
    if argument_information["optional"]:
        optional_addendum = '=None'

    # hi:str=None or hi:str
    return f"{argument_name}:{argument_type.__name__}{optional_addendum}"



def encode_decorator(decorator_type, decorator_values):
    stringified_arguments = []
    for command_argument in decorator_values:
         stringified_arguments.append(f"{command_argument}={str(decorator_values[command_argument])}")
    function_arguments = ','.join(stringified_arguments)
    return f"@app_commands.{decorator_type}({function_arguments})"

 # def autocomplete_possible_moves(self, argument_name, current, player):
 #        moves = {'00': 'Top Left', '01': 'Top Mid', '02': 'Top Right', '10': 'Mid Left', '11': 'Mid Mid', '12': 'Mid Right', '20': 'Bottom Left', '21': 'Bottom Mid', '22': 'Bottom Right'}
 #
 #        if argument_name == "move":
 #            available_moves = [i for i in moves if (i in self.get_player_moves(player.id)) and (current in moves[i])]
 #            return available_moves

def build_function_definitions():
    context = []
    for game in GAME_TYPES:
        # Import the game's module
        game_class = getattr(importlib.import_module(GAME_TYPES[game][0]), GAME_TYPES[game][1])
        options: list[InputType] = game_class.options  # Get the game's defined move option set
        decorators = {}
        arguments = {}

        for option in options:
            # Obtain the decorators and arguments that the option uses
            option_decorators = option.decorators()

            # Autocomplete check
            if "autocomplete" not in option_decorators and option.autocomplete is not None:
                option_decorators.update({"autocomplete": {option.name: "autocomplete_"+option.autocomplete}})

            option_arguments = option.arguments()

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

        command_name = game+"_move"


        move_command = (f"{'\n'.join(encoded_decorators)}\n"
                        f"@move_group.command(name='{game}', description='move i guess')\n"
                        f"async def {command_name}(ctx, {','.join(encoded_arguments)}):\n"
                        f"  await ctx.response.defer()\n"
                        f"  await handle(ctx=ctx, arguments=locals())\n")

        if "autocomplete" in decorators.keys():  # If there is any autocomplete support for this command
            for autocomplete in decorators["autocomplete"]:
                ac_command_name = decorators["autocomplete"][autocomplete]

                ac_command = (f"async def {ac_command_name}(ctx, current):\n"
                              f"   return await handle_autocomplete(ctx, current, \"{autocomplete}\")\n")

                context.append(ac_command)

        context.append(move_command)



    return context




if __name__ == "__main__":
    try:
        move_commands = build_function_definitions()  # Build game move callbacks

        # Register commands
        for command in move_commands:
            print(command)
            exec(command)  # Add the command

    except Exception as e:
        raise e
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