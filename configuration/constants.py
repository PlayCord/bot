import discord

from utils.locale import fmt, get, get_dict

VERSION = "0.3.0"
IS_ACTIVE = True
NAME = get("brand.name")
MANAGED_BY = get("meta.author")
LOGGING_ROOT = "playcord"
MESSAGE_COMMAND_FAILED = "⛔"
MESSAGE_COMMAND_SUCCEEDED = "✅"
MESSAGE_COMMAND_PENDING = "⏳"

MESSAGE_COMMAND_DISABLE = "disable"
MESSAGE_COMMAND_ENABLE = "enable"
MESSAGE_COMMAND_TOGGLE = "toggle"
MESSAGE_COMMAND_SYNC = "sync"
MESSAGE_COMMAND_CLEAR = "clear"
MESSAGE_COMMAND_ANALYTICS = "analytics"
MESSAGE_COMMAND_TREEDIFF = "treediff"
MESSAGE_COMMAND_SPECIFY_LOCAL_SERVER = "this"

OWNERS = [897146430664355850, 1085939954758205561]
CONFIGURATION = {}

WELCOME_MESSAGE = [
    (
        fmt("welcome.title", name=NAME),
        fmt("welcome.description"),
    ),
    (get("welcome.fields.games.name"), get("welcome.fields.games.value")),
    (get("welcome.fields.rating.name"), get("welcome.fields.rating.value")),
    (
        get("welcome.fields.help.name"),
        fmt("welcome.fields.help.value", github_url=get("brand.github_url")),
    ),
]

# Standardized embed colors for consistent UX
EMBED_COLOR = discord.Color.from_str("#6877ED")  # Primary brand color (purple-blue)
ERROR_COLOR = discord.Color.from_str("#ED6868")  # Errors and failures (red)
INFO_COLOR = discord.Color.from_str("#9A9CB0")  # Informational embeds (gray)
SUCCESS_COLOR = discord.Color.from_str("#68ED7B")  # Success messages (green)
WARNING_COLOR = discord.Color.from_str("#EDC868")  # Warnings and cautions (yellow/orange)
GAME_COLOR = discord.Color.from_str("#68D4ED")  # Game-related embeds (cyan)
MATCHMAKING_COLOR = discord.Color.from_str("#B068ED")  # Matchmaking/lobby embeds (purple)

CONFIG_BOT_SECRET = "secret"

CONFIG_FILE = "configuration/config.yaml"
EMOJI_CONFIGURATION_FILE = "configuration/emoji.yaml"

ERROR_IMPORTED = "This file is NOT designed to be imported. Please run bot.py directly!"
ERROR_NO_SYSTEM_CHANNEL = "No system channel is set - not sending anything."
ERROR_INCORRECT_SETUP = ("This is likely due to:\n"
                         "1. Internet issues\n"
                         "2. Incorrect discord token\n"
                         "3. Incorrectly set up discord bot")

GAME_TYPES = {
    "tictactoe": ["games.TicTacToe", "TicTacToeGame"],
    "liars": ["games.LiarsDice", "LiarsDiceGame"],
    "test": ["games.TestGame", "TestGame"],
    "connectfour": ["games.ConnectFour", "ConnectFourGame"],
    "reversi": ["games.Reversi", "ReversiGame"],
    "nim": ["games.Nim", "NimGame"],
    "mastermind": ["games.MastermindDuel", "MastermindDuelGame"],
    "battleship": ["games.Battleship", "BattleshipGame"],
    "nothanks": ["games.NoThanks", "NoThanksGame"],
    "blackjack": ["games.BlackjackTable", "BlackjackTableGame"],
    "poker": ["games.Poker", "PokerGame"],
    "chess": ["games.Chess", "ChessGame"],
}

MU = 1000
GAME_TRUESKILL = {
    "tictactoe": {"sigma": 1 / 6, "beta": 1 / 12, "tau": 1 / 100, "draw": 9 / 10},
    "liars": {"sigma": 1 / 2.5, "beta": 1 / 5, "tau": 1 / 250, "draw": 0},
    "test": {"sigma": 1 / 3, "beta": 1 / 5, "tau": 1 / 250, "draw": 0},
    "connectfour": {"sigma": 1 / 6, "beta": 1 / 12, "tau": 1 / 120, "draw": 1 / 10},
    "reversi": {"sigma": 1 / 5, "beta": 1 / 10, "tau": 1 / 150, "draw": 1 / 20},
    "nim": {"sigma": 1 / 4, "beta": 1 / 8, "tau": 1 / 150, "draw": 0},
    "mastermind": {"sigma": 1 / 4, "beta": 1 / 8, "tau": 1 / 180, "draw": 0},
    "battleship": {"sigma": 1 / 4, "beta": 1 / 8, "tau": 1 / 180, "draw": 0},
    "nothanks": {"sigma": 1 / 3, "beta": 1 / 6, "tau": 1 / 200, "draw": 0},
    "blackjack": {"sigma": 1 / 3, "beta": 1 / 6, "tau": 1 / 200, "draw": 1 / 5},
    "poker": {"sigma": 1 / 3, "beta": 1 / 6, "tau": 1 / 200, "draw": 0},
    "chess": {"sigma": 1 / 5, "beta": 1 / 10, "tau": 1 / 150, "draw": 1 / 10},
}

TEXTIFY_CURRENT_GAME_TURN = get_dict("game.turn")

# Textify options for game started messages
TEXTIFY_GAME_STARTED = get_dict("game.started")

# Textify options for join button text
TEXTIFY_BUTTON_JOIN = get_dict("buttons.textify.join")

# Textify options for leave button text
TEXTIFY_BUTTON_LEAVE = get_dict("buttons.textify.leave")

# Textify options for start button text
TEXTIFY_BUTTON_START = get_dict("buttons.textify.start")

# Textify options for game over messages
TEXTIFY_GAME_OVER = get_dict("game.over")

# Textify options for draw messages
TEXTIFY_GAME_DRAW = get_dict("game.draw")

# Current ongoing games
# Format:
# {game thread id: GameInterface object}
CURRENT_GAMES = {}
CURRENT_MATCHMAKING = {}

IN_GAME = {}  # user id: gameinterface
IN_MATCHMAKING = {}  # user id: matchmakinginterface

AUTOCOMPLETE_CACHE = {}

# game_id
# - user_id
# - - current: autocompletes

LONG_SPACE_EMBED = "\u2800"  # discord hides spaces when there is more than one in a row, this fixes it

# Button custom_id prefixes
BUTTON_PREFIX_JOIN = "join/"
BUTTON_PREFIX_LEAVE = "leave/"
BUTTON_PREFIX_START = "start/"
BUTTON_PREFIX_LOBBY_OPT = "lobbyopt/"
BUTTON_PREFIX_SELECT_CURRENT = "select_c/"
BUTTON_PREFIX_SELECT_NO_TURN = "select_n/"
BUTTON_PREFIX_CURRENT_TURN = "c/"
BUTTON_PREFIX_NO_TURN = "n/"
BUTTON_PREFIX_INVITE = "invite/"
BUTTON_PREFIX_SPECTATE = "spectate/"
BUTTON_PREFIX_PEEK = "peek/"

# Pagination button custom_id prefixes
BUTTON_PREFIX_PAGINATION_FIRST = "pagination_first/"
BUTTON_PREFIX_PAGINATION_PREV = "pagination_prev/"
BUTTON_PREFIX_PAGINATION_NEXT = "pagination_next/"
BUTTON_PREFIX_PAGINATION_LAST = "pagination_last/"
BUTTON_PREFIX_REMATCH = "rematch/"

PRESENCE_TIMEOUT = 60
PRESENCE_PRESETS = [
    fmt("presence.with_name", name=NAME),
    get("presence.games_with_friends"),
    get("presence.play_catalog"),
]

# Permission and policy messages
PERMISSION_MSG_NOT_PARTICIPANT = get("permissions.not_participant")
PERMISSION_MSG_SPECTATE_DISABLED = get("permissions.spectate_disabled")
PERMISSION_MSG_WRONG_CHANNEL = get("permissions.wrong_channel")
PERMISSION_MSG_NO_GAME_HERE = get("permissions.no_game_here")
PERMISSION_MSG_NOT_YOUR_TURN = get("permissions.not_your_turn")

# Thread policy settings
THREAD_POLICY_WARN_NON_PARTICIPANTS = True  # Warn users who message in game threads without being participants
THREAD_POLICY_DELETE_NON_PARTICIPANT_MESSAGES = False  # Delete messages from non-participants (more aggressive)
THREAD_POLICY_WARNING_MESSAGE = get("thread_policy.warning")
# If True, participants may only send messages that look like slash usage (start with '/') in active game threads
THREAD_POLICY_PARTICIPANTS_COMMANDS_ONLY = False
# When True, always delete messages from users who are not match participants (e.g. spectators), even if
# THREAD_POLICY_DELETE_NON_PARTICIPANT_MESSAGES is False.
THREAD_POLICY_SPECTATORS_SILENT = False
