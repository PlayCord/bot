import discord

NAME = "Tyler's Demise"
RUNTIME_EMOJIS = None
LOGGING_ROOT = "playcord"
SERVER_TIMEOUT = 5000

MESSAGE_COMMAND_FAILED = "⛔"
MESSAGE_COMMAND_SUCCEEDED = "✅"

MESSAGE_COMMAND_DISABLE = "disable"
MESSAGE_COMMAND_ENABLE = "enable"
MESSAGE_COMMAND_TOGGLE = "toggle"
MESSAGE_COMMAND_SYNC = "sync"
MESSAGE_COMMAND_SYNC_LOCAL_SERVER = "this"

OWNERS = [897146430664355850]


WELCOME_MESSAGE = [
    (f"Hi! I'm {NAME}!", "Thanks for adding me to your server :D\nHere's some tips on how to get started.\n"
                          "Please note that this introduction (or the bot) doesn't contain details on how to"
                          " use the bot. For that, please check the README (linked below)."),
    ("What is this bot?", f"{NAME} is a bot for playing any variety of quick game on Discord."),
    ("Where's the README?", "Right [here](https://github.com/quantumbagel/PlayCord/blob/master/README.md) :D"),
    ("Who made you?", "[@quantumbagel on Github](https://github.com/quantumbagel)")
]

EMBED_COLOR = discord.Color.from_rgb(255, 87, 51)


CONFIG_BOT_SECRET = "secret"
CONFIG_MONGODB_URI = "mongodb"

CONFIG_FILE = "configuration/config.yaml"


ERROR_IMPORTED = "This file is NOT designed to be imported. Please run bot.py directly!"
ERROR_NO_SYSTEM_CHANNEL = "No system channel is set - not sending anything."
ERROR_INCORRECT_SETUP = ("This is likely due to:\n"
                         "1. Internet issues\n"
                         "2. Incorrect discord token\n"
                         "3. Incorrectly set up discord bot")

GAME_TYPES = {"tic_tac_toe": ["utils.TicTacToeGame", "TicTacToeGame"]}