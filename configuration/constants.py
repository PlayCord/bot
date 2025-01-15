import discord

VERSION = "dev12"
IS_ACTIVE = True
NAME = "PlayCord"
RUNTIME_EMOJIS = None
LOGGING_ROOT = "playcord"
SERVER_TIMEOUT = 5000

MESSAGE_COMMAND_FAILED = "⛔"
MESSAGE_COMMAND_SUCCEEDED = "✅"

MESSAGE_COMMAND_DISABLE = "disable"
MESSAGE_COMMAND_ENABLE = "enable"
MESSAGE_COMMAND_TOGGLE = "toggle"
MESSAGE_COMMAND_SYNC = "sync"
MESSAGE_COMMAND_CLEAR = "clear"
MESSAGE_COMMAND_SPECIFY_LOCAL_SERVER = "this"

OWNERS = [897146430664355850, 1085939954758205561]
CONFIGURATION = {}

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

GAME_TYPES = {"tictactoe": ["games.TicTacToeGame", "TicTacToeGame"]}

MU = 1000
GAME_TRUESKILL = {"tictactoe": {"sigma": 1/6,
                                  "beta": 1/12,
                                  "tau": 1/100,
                                  "draw": 9/10}}


TEXTIFY_CURRENT_GAME_TURN = {
    "It's {player}'s turn to play.": 0.529,
    "Next up: {player}.": 0.45,
    "We checked the books, and it is *somehow* {player}'s turn to play. Not sure how that happened.": 0.01,
    "After journeying the Himalayas for many a year, we now know that it's {player}'s turn!": 0.01,
    "Did you know that the chance of this turn message appearing is 0.1%?. alsobythewayit's{player}'sturn": 0.001

}


SIGMA_RELATIVE_UNCERTAINTY_THRESHOLD = 0.20

# Current ongoing games
# Format:
# {game thread id: GameInterface object}
CURRENT_GAMES = {}
CURRENT_MATCHMAKING = {}


IN_GAME = {} # user id: gameinterface
IN_MATCHMAKING = {}  # user id: matchmakinginterface


AUTOCOMPLETE_CACHE = {}

# game_id
# - user_id
# - - current: autocompletes


LONG_SPACE_EMBED = "\u2800"  # discord hides spaces when there is more than one in a row, this fixes it
