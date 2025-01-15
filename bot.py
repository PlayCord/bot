import importlib
import logging
import sys
import traceback
from symtable import Function
from typing import Any

import discord
import trueskill
from discord import app_commands, ChannelType, Member, User
from discord.app_commands import Choice, Group
import utils.logging_formatter
from configuration.constants import *
import configuration.constants as constants
from ruamel.yaml import YAML

from utils import Database, CommandType
from utils.CustomEmbed import CustomEmbed, ErrorEmbed
from utils.Database import get_player
from utils.GameInterface import GameInterface, MatchmakingInterface, MatchmakingView, InviteView
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
        return
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



async def send_simple_embed(ctx: discord.Interaction, title: str, description: str, ephemeral: bool = True,
                            responded: bool = False) -> None:
    """
    Generate a simple embed
    :param title: the title
    :param description: the description
    :return: the embed
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


    if not IS_ACTIVE:  # Bot disabled via mesage command
        await send_simple_embed(ctx, "Bot has been disabled!", f"{NAME} "
                                      f"has been temporarily disabled by a bot owner. This"
                                      " is likely due to a critical bug or exploit being discovered.")
        return False

    if ctx.user.bot:  # We don't want no bots
        logger.warning("Bot users are not allowed to use commands.")
        return False

    return True


command_root.interaction_check = interaction_check  # Set the interaction check


@client.event
async def on_interaction(ctx: discord.Interaction):
    """
    Callback activated after every bot interaction. For the purposes of this bot,
     this is used to handle button interactions.
    :param ctx:
    :return:
    """
    # Log interaction
    log.getChild("event.on_interaction").debug(f"Interaction of type '{ctx.type}' received: {ctx.data}")

    custom_id = ctx.data.get("custom_id")  # Get custom ID
    if custom_id is None:  # Not button
        return

    if custom_id.startswith("invite/"):  # Invite accept button
        await invite_accept_callback(ctx)
    if custom_id.startswith("spectate/"):  # Spectate button
        await spectate_callback(ctx)

@client.event
async def on_ready():
    """
    Callback activated after the bot is ready (connected to gateway).
    Only things we need to do is register button views and rich presence.
    :return:
    """
    # Register views to the bot
    client.add_view(MatchmakingView())
    activity = discord.Activity(type=discord.ActivityType.playing,
                                   name="paper and pencil games on discord!", state=f"Watching {len(client.guilds)} servers!")
    await client.change_presence(activity=activity, status=discord.Status.online)


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
        if len(split) == 1:  # just /sync
            try:
                await tree.sync()
            except discord.app_commands.errors.CommandSyncFailure as e:
                await msg.add_reaction(MESSAGE_COMMAND_FAILED)
                await msg.reply(embed=ErrorEmbed(f"Couldn't sync commands! ({type(e)})", traceback.format_exc()))
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
                await msg.reply(embed=ErrorEmbed(f"Couldn't sync commands! ({type(e)})", traceback.format_exc()))
                return
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

async def invite_accept_callback(ctx: discord.Interaction):
    await ctx.response.defer()  # Prevent button interaction from failing
    matchmaker_id: str = ctx.data['custom_id'].replace('invite/', "")
    if int(matchmaker_id) in CURRENT_MATCHMAKING:
        matchmaker: MatchmakingInterface = CURRENT_MATCHMAKING[int(matchmaker_id)]
        error = await matchmaker.accept_invite(ctx.user)
        if error is not None:
            await ctx.followup.send(error, ephemeral=True)
            return
        await ctx.followup.send("You have joined the game! Press 'Go To Game' to go to the server where the game is", ephemeral=True)
    else:
        await ctx.followup.send("This invite has expired.", ephemeral=True)
    view = discord.ui.View.from_message(ctx.message)
    for button in view.children:
        if button.custom_id == "invite/"+matchmaker_id:
            button.disabled = True
    await ctx.message.edit(view=view, embed=ctx.message.embeds[0])


async def spectate_callback(ctx: discord.Interaction):
    await ctx.response.defer()



@command_root.command(name="invite", description="Invite a player to play a game, or remove them from the blacklist in public games.")
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
    invited_users = {user, user2, user3, user4, user5}  # Condense to unique users

    id_matchmaking = {p.id: q for p, q in IN_MATCHMAKING.items()}  # get matchmaking by player ID

    if ctx.user.id not in id_matchmaking:  # Player isn't in matchmaking
        await ctx.response.send_message("You aren't in matchmaking, so you can't invite people to play.",
                                        ephemeral=True)  # TODO: invites start games
        return

    matchmaker: MatchmakingInterface = id_matchmaking[ctx.user.id]  # Get the matchmaker for the game the player is in

    if matchmaker.private and matchmaker.creator.id != ctx.user.id:  # Only creators can invite in private games
        await ctx.response.send_message("You aren't the creator of this game, so you can't invite people to play.",
                                        ephemeral=True)
        return

    game_type = matchmaker.game.name

    failed_invites = {}
    for invited_user in filter(None, invited_users):  # Filter out None values
        if invited_user not in matchmaker.message.guild.members:
            failed_invites[invited_user] = "Member was not in server that the game was"
            continue
        if invited_user.id in [p.id for p in matchmaker.queued_players]:
            failed_invites[invited_user] = "Member was already in matchmaking."
            continue
        if invited_user in IN_GAME:
            failed_invites[invited_user] = "Member was already in a game."
            continue
        if invited_user.bot:
            failed_invites[invited_user] = "Member was a bot :skull:."
            continue
        embed = CustomEmbed(title=f"👋 Do you want to play a game?", description=f"{ctx.user.mention} has invited you to play a game of {game_type} in \"{matchmaker.message.guild.name}.\" If you don't want to play, just ignore this message.")

        await invited_user.send(embed=embed, view=InviteView(join_button_id="invite/"+str(matchmaker.message.id), game_link=matchmaker.message.jump_url))
        continue
    if not len(failed_invites):
        await ctx.response.send_message("Invites sent successfully.", ephemeral=True)
        return
    elif len(failed_invites) == len(invited_users):
        message = "Failed to send any invites. Errors:"
    else:
        message = "Failed to send invites to the following users:"

    final = message + "\n"
    for fail in failed_invites:
        final += f"{fail.mention} - {failed_invites[fail]}\n"
    await ctx.response.send_message(final, ephemeral=True)

@command_root.command(name="kick", description="Remove a user from your lobby without banning them.")
async def command_kick(ctx: discord.Interaction, user: discord.User, reason: str = None):
    """

    :param ctx:
    :param user:
    :param reason:
    :return:
    """
    id_matchmaking = {p.id: q for p, q in IN_MATCHMAKING.items()}

    if ctx.user.id not in id_matchmaking:
        await ctx.response.send_message("You aren't in matchmaking, so you can't kick anyone.",
                                        ephemeral=True)
        return
    matchmaker: MatchmakingInterface = id_matchmaking[ctx.user.id]
    if matchmaker.creator.id != ctx.user.id:
        await ctx.response.send_message("You aren't the creator of this game, so you can't kick people from the game.",
                                        ephemeral=True)
        return

    return_value = await matchmaker.kick(user, reason)

    await ctx.response.send_message(return_value, ephemeral=True)

@command_root.command(name="ban", description="Either removes a user from the whitelist (private games)"
                                              "or adds them to the blacklist (public games)")
async def command_ban(ctx: discord.Interaction, user: discord.User, reason: str = None):
    id_matchmaking = {p.id: q for p, q in IN_MATCHMAKING.items()}

    if ctx.user.id not in id_matchmaking:
        await ctx.response.send_message("You aren't in matchmaking, so you can't ban anyone.",
                                        ephemeral=True)
        return
    matchmaker: MatchmakingInterface = id_matchmaking[ctx.user.id]
    if matchmaker.creator.id != ctx.user.id:
        await ctx.response.send_message("You aren't the creator of this game, so you can't ban people from the game.",
                                        ephemeral=True)
        return

    return_value = await matchmaker.ban(user, reason)

    await ctx.response.send_message(return_value, ephemeral=True)
    pass



@command_root.command(name="stats", description="Get stats about the bot")
async def command_stats(ctx: discord.Interaction):
    server_count = len(client.guilds)
    member_count = len(set(client.get_all_members()))

    shard_id = ctx.guild.shard_id

    shard_ping = client.latency
    shard_servers = len([guild for guild in client.guilds if guild.shard_id == shard_id])

    embed = CustomEmbed(title='PlayCord Stats <:pointing:1328138400808828969>')

    embed.add_field(name='💻 Bot Version:', value=VERSION)
    embed.add_field(name='🐍 discord.py Version:', value=discord.__version__)
    embed.add_field(name='Total Guilds:', value=server_count)
    embed.add_field(name='<:user:1328138963512201256> Total Users:', value=member_count)
    embed.add_field(name='#️⃣ Shard ID:', value=shard_id)
    embed.add_field(name='🛜 Shard Ping:', value=str(round(shard_ping*100, 2)) + " ms")
    embed.add_field(name='Shard Guilds:', value=shard_servers)
    embed.add_field(name='👾 Games Loaded:', value=len(GAME_TYPES))

    await ctx.response.send_message(embed=embed)

@command_root.command(name="about", description="About the bot")
async def command_about(ctx: discord.Interaction):



    embed = CustomEmbed(title='About PlayCord 🎲')
    embed.add_field(name="Bot by:", value="[@quantumbagel](https://github.com/quantumbagel)")
    embed.add_field(name="Source code:", value="[here](https://github.com/quantumbagel/PlayCord)")
    embed.add_field(name="Cats", value="3 UwU 🐈‍⬛🐈‍⬛🐈‍⬛")
    embed.add_field(name="Libraries used:", value="discord.py\nsvg.py\nruamel.yaml\ncairosvg\ntrueskill\nmpmath", inline=False)
    embed.set_footer(text="©	️2025 Julian Reder. All rights reserved. Except the 3rd.")

    await ctx.response.send_message(embed=embed)


@command_root.command(name="tictactoe", description="Tic-Tac Toe is a game about replacing your toes with Tic-Tacs, obviously.")
async def tictactoe(ctx: discord.Interaction, rated: bool = True, private: bool = False):


    if not (ctx.channel.permissions_for(ctx.guild.me).create_private_threads
            and ctx.channel.permissions_for(ctx.guild.me).send_messages):  # Don't make the bot look stupid
        await send_simple_embed(ctx, title="Insufficient Permissions", description="Bot is missing permissions to function in this channel.", ephemeral=True)
        return

    if ctx.channel.type == discord.ChannelType.public_thread or ctx.channel.type == discord.ChannelType.private_thread:
        await send_simple_embed(ctx, title="Invalid Channel Type",
                                description="This command cannot be run in public or private threads.", ephemeral=True)

    await ctx.response.send_message(embed=CustomEmbed(description="<a:loading:1318216218116620348>").remove_footer())
    thing = await ctx.original_response()



    g = MatchmakingInterface(ctx.user, "tictactoe", thing, rated=rated, private=private)

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


async def handle_move(ctx: discord.Interaction, name, arguments):
    if ctx.channel.type != discord.ChannelType.private_thread:
        await send_simple_embed(ctx, "Move commands can only be run in their respective threads",
                                "Please use a bot-created thread to move. :)", responded=True)
        return
    if ctx.channel.id not in CURRENT_GAMES.keys():
        await send_simple_embed(ctx, "Move commands can only be run in their respective threads",
                                "Please use a bot-created thread to move. :)", responded=True)
        return
    arguments.pop("ctx")
    arguments = {a: await decode_discord_arguments(arguments[a]) for a in arguments.keys()}
    print(arguments)
    AUTOCOMPLETE_CACHE[ctx.channel.id] = {}  # Reset autocomplete cache
    await CURRENT_GAMES[ctx.channel.id].move(ctx, name, arguments)


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
    logger = log.getChild("autocomplete")
    try:
        game_view = CURRENT_GAMES[ctx.channel.id]
    except KeyError:  # Game not in this channel
        logger.info(f"There is no game from channel #{ctx.channel.mention} (id={ctx.channel.id}). Not autocompleting.")
        return [app_commands.Choice(name="There is no game in this channel!", value="")]

    player = get_player(game_view.game_type, ctx.user)  # Get the player who called this function
    try:
        player_options = AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id][function][argument][current]
        logger.info(f"Successfully used autocomplete cache: channel_id={ctx.channel.id}, user_id={ctx.user.id}, function={function} argument={argument}, current=\"{current}\"")
    except KeyError:
        ac_callback = None
        for move in game_view.game.moves:
            for option in move.options:
                if option.name == argument:
                    # Get the autocomplete callback for this argument
                    # This MUST exist because this function was called
                    ac_callback = getattr(game_view.game, option.autocomplete)
                    break

        if not option.force_reload:
            try:
                # Get the options for the player from the backend
                player_options = ac_callback(player)
                if ctx.channel.id not in AUTOCOMPLETE_CACHE:
                    AUTOCOMPLETE_CACHE[ctx.channel.id] = {}
                if ctx.user.id not in AUTOCOMPLETE_CACHE[ctx.channel.id]:
                    AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id] = {}
                if function not in AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id]:
                    AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id][function] = {}
                if argument not in AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id][function]:
                    AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id][function][argument] = {}
                AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id][function][argument].update({current: player_options})
            except TypeError:
                logger.critical(f"handle_autocomplete was called without a matching callback function."
                                f" channel_id={ctx.channel.id}, user_id={ctx.user.id}, function={function} argument={argument},"
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


def build_function_definitions() -> dict[Group, list[Any]]:
    """
    Build the dynamic functions

    This includes:
    move commands
    autocomplete callbacks

    :return: a list of strings each representing a function that needs to be added to the global
    """
    context = {}
    for game in GAME_TYPES:  # for each registered game
        # Import the game's module
        game_class = getattr(importlib.import_module(GAME_TYPES[game][0]), GAME_TYPES[game][1])  # Get the game's class


        moves: list[CommandType] = game_class.moves  # Get the game's defined move option set

        # Decorators and arguments to build from
        decorators = {}
        arguments = {}

        for move in moves:
            temp_decorators = {}
            temp_arguments = {}
            for option in move.options:
                # Obtain the decorators and arguments that the option uses
                option_decorators = option.decorators()

                # Autocomplete check
                if "autocomplete" not in option_decorators and option.autocomplete is not None:
                    option_decorators.update({"autocomplete": {option.name: "autocomplete_"+option.autocomplete}})

                option_arguments = option.arguments()  # Get the arguments

                # Add each argument
                for argument in option_arguments:
                    temp_arguments.update({argument: option_arguments[argument]})

                # Add each decorator, but some extra logic for stacking multiple variables of same decorator type
                for decorator in option_decorators.keys():
                    if decorator not in decorators.keys():
                        temp_decorators[decorator] = option_decorators[decorator]
                    else:
                        temp_decorators[decorator].update({decorator: option_decorators[decorator]})
            decorators[move.name] = temp_decorators
            arguments[move.name] = temp_arguments



        for this_move in moves:
            # Encode decorators to text
            encoded_decorators = []

            this_move_decorators = decorators[this_move.name]
            this_move_arguments = arguments[this_move.name]

            dynamic_command_group = app_commands.Group(name=game, description=game_class.command_description)
            context[dynamic_command_group] = []


            for unencoded_decorator in this_move_decorators:
                encoded_decorators.append(encode_decorator(unencoded_decorator, this_move_decorators[unencoded_decorator]))

            # Encode arguments to text
            encoded_arguments = []
            for unencoded_argument in this_move_arguments:
                encoded_arguments.append(encode_argument(unencoded_argument, this_move_arguments[unencoded_argument]))

            command_name = game+"_"+this_move.name  # Name of move command to register


            # Build the move command
            move_command = (f"{'\n'.join(encoded_decorators)}\n"
                            f"@group.command(name='{this_move.name}', description='{this_move.description}')\n"
                            f"async def {command_name}(ctx, {','.join(encoded_arguments)}):\n"
                            f"  await ctx.response.defer(ephemeral=True)\n"
                            f"  await handle_move(ctx=ctx, name=\"{this_move.name}\", arguments=locals())\n")

            if "autocomplete" in this_move_decorators.keys():  # If there is any autocomplete support for this command
                for autocomplete in this_move_decorators["autocomplete"]:

                    # Name of autocomplete command
                    ac_command_name = this_move_decorators["autocomplete"][autocomplete]

                    # Actual autocomplete command
                    ac_command = (f"async def {ac_command_name}(ctx, current):\n"
                                  f"   return await handle_autocomplete(ctx, \"{this_move.name}\", current, \"{autocomplete}\")\n")

                    # Add the autocomplete command
                    context[dynamic_command_group].append(ac_command)

            # Add the move command, so autocomplete callbacks are built before the move command
            context[dynamic_command_group].append(move_command)


    return context


if __name__ == "__main__":
    try:
        commands = build_function_definitions()  # Build game move callbacks
        log.info(f"Built {len(commands)} hooks.")
        # Register commands
        for group in commands:
            tree.add_command(group)
            for command in commands[group]:
                exec(command)  # Add the command

        log.info(f"Hooks registered.")


    except Exception as e:
        log.critical(str(e))
        log.critical("Error registering bot commands!")
        raise e
    try:

        # Add command groups to tree
        tree.add_command(command_root)
        tree.add_command(move_group)

        # Run the bot :)
        client.run(config[CONFIG_BOT_SECRET], log_handler=None)
    except Exception as e:  # Something went wrong
        log.critical(str(e))
        log.critical(ERROR_INCORRECT_SETUP)