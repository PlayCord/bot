# PlayCord
import json
import logging
import sys
import time
from xmlrpc.client import SYSTEM_ERROR

import discord
import pymongo.errors
from discord import app_commands
from discord.app_commands import command
from pymongo import MongoClient

import utils.logging_formatter
from configuration.constants import *
from ruamel.yaml import YAML

from utils.GameView import GameView, MatchmakingView

logging.getLogger("discord").setLevel(logging.INFO)  # Discord.py logging level - INFO (don't want DEBUG)
logging.getLogger("pymongo").setLevel(logging.INFO)  # Mongodb logging level - INFO (don't want DEBUG)

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
    try:
        loaded_config_file = YAML().load(open(CONFIG_FILE))
    except FileNotFoundError:
        log.critical("Configuration file not found.")
        return None
    log.debug("Successfully loaded configuration file!")
    return loaded_config_file

config = load_configuration()


IS_ACTIVE = True




client = discord.Client(intents=discord.Intents.all())
tree = app_commands.CommandTree(client)  # Build command tree

db = None

def connect_to_database():
    global db
    db = MongoClient(host=config[CONFIG_MONGODB_URI], serverSelectionTimeoutMS=SERVER_TIMEOUT)
    try:
        db.aprivatein.command('ismaster')  # Cheap command to block until connected/timeout
    except pymongo.errors.ServerSelectionTimeoutError:
        log.critical(f"Failed to connect to MongoDB database (uri=\"{config[CONFIG_MONGODB_URI]}\")")
        return False
    return True

while True:
    if connect_to_database():
        break
log.debug("Successfully connected to MongoDB!")
# watching_commands_access = db_client['commands']
command_root = app_commands.Group(name=LOGGING_ROOT, description="The heart and soul of the game.")  # The command group
# I don't think that description is visible anywhere, but maybe it is lol.
log.info(f"Welcome to {NAME} by @quantumbagel!")


def set_bagel_footer(embed: discord.Embed):
    embed.set_footer(text=f"Made with ❤ by @quantumbagel",
                     icon_url="https://avatars.githubusercontent.com/u/58365715")

def generate_simple_embed(title: str, description: str) -> discord.Embed:
    """
    Generate a simple embed
    :param title: the title
    :param description: the description
    :return: the embed
    """
    embed = discord.Embed(title=title, description=description, color=EMBED_COLOR)
    set_bagel_footer(embed)

    return embed


async def send_simple_embed(ctx: discord.Interaction, title: str, description: str, ephemeral: bool = True):
    """
    Generate a simple embed
    :param title: the title
    :param description: the description
    :return: the embed
    """
    ctx.response.send_message(embed=generate_simple_embed(title, description), ephemeral=ephemeral)


@command_root.interaction_check
async def is_allowed(ctx: discord.Interaction) -> bool:
    """
    Returns if an interaction should be allowed.
    This checks for:
    * Bot user
    * DM
    * Role permission / positioning if no role set
    :param ctx: the Interaction to checker
    :param f_log: the logger
    :return: true or false
    """
    f_log = log.getChild("is_allowed")
    if not IS_ACTIVE:
        embed = generate_simple_embed("Bot has been disabled!",
                                      f"{NAME} has been temporarily disabled by @quantumbagel. This"
                                      " is likely due to a critical bug being discovered.")
        await ctx.response.send_message(embed=embed, ephemeral=True)
        return False
    if ctx.user.bot:
        f_log.warning("Bot users are not allowed to use commands.")
        return False
    if str(ctx.channel.type) == "private":  # No DMs - yet
        f_log.error("Commands don't work in DMs!")
        embed = generate_simple_embed("Commands don't work in DMs!",
                                      f"{NAME} is a server-only bot currently. requires a server for its commands to work."
                                      " Support for some DM commands may come in the future.")
        await ctx.response.send_message(embed=embed, ephemeral=True)
        return False

    return True



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
    if msg.content.startswith(f"{LOGGING_ROOT}/{MESSAGE_COMMAND_SYNC}") and msg.author.id in OWNERS:  # Perform sync
        split = msg.content.split()
        if len(split) == 1:
            await tree.sync()
        else:
            if split[1] == MESSAGE_COMMAND_SYNC_LOCAL_SERVER:
                g = msg.guild
            else:
                g = discord.Object(id=int(split[1]))
            tree.copy_global_to(guild=g)
            await tree.sync(guild=g)
        f_log.info(f"Performed authorized sync from user {msg.author.id}")
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






@client.event
async def on_guild_join(guild: discord.Guild) -> None:
    """
    Send a message to guilds when the bot is added.
    :param guild: the guild the bot was added to
    :return: nothing
    """
    f_log = log.getChild("event.guild_join")
    f_log.info("Added to guild \"" + guild.name + f"\"! (id={guild.id})")
    embed = discord.Embed(title=WELCOME_MESSAGE[0][0],
                          description=WELCOME_MESSAGE[0][1],
                          color=EMBED_COLOR)
    for line in WELCOME_MESSAGE[1:]:
        embed.add_field(name=line[0], value=line[1])
    set_bagel_footer(embed)

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



@command_root.command(name="tictactoe", description="game test")
async def tictactoe(ctx: discord.Interaction):
    await ctx.response.defer()
    message = ctx.followup
    g = MatchmakingView(ctx.user, "tic_tac_toe", message)
    await g.generate_embed()

if __name__ == "__main__":
    RUNTIME_EMOJIS = client.emojis
    try:
        tree.add_command(command_root)
        client.run(config[CONFIG_BOT_SECRET], log_handler=None)
    except Exception as e:
        log.critical(str(e))
        log.critical(ERROR_INCORRECT_SETUP)
else:
    log.critical(ERROR_IMPORTED)