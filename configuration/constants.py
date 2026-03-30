import discord

VERSION = "0.1.1"
IS_ACTIVE = True
NAME = "PlayCord"
MANAGED_BY = "quantumbagel"
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
    (f"👋 Welcome to {NAME}!", 
     f"Thanks for adding me! I'm a Discord bot for playing turn-based games with friends.\n\n"
     f"**Quick Start:**\n"
     f"• `/play <game>` - Start a new game\n"
     f"• `/playcord catalog` - Browse all games\n"
     f"• `/playcord help` - Interactive help menu"),
    ("🎮 Available Games", 
     "I have over 10 games including Tic-Tac-Toe, Connect Four, Chess, Poker, and more! "
     "Each game tracks your rating so you can compete for the leaderboard."),
    ("📊 Rating System", 
     "Every game has a skill-based rating system. Win games to climb the leaderboard "
     "and show off your skills!"),
    ("❓ Need Help?", 
     "Use `/playcord help` for an interactive guide, or check out our "
     "[GitHub](https://github.com/PlayCord/bot) for documentation.")
]

# Standardized embed colors for consistent UX
EMBED_COLOR = discord.Color.from_str("#6877ED")      # Primary brand color (purple-blue)
ERROR_COLOR = discord.Color.from_str("#ED6868")      # Errors and failures (red)
INFO_COLOR = discord.Color.from_str("#9A9CB0")       # Informational embeds (gray)
SUCCESS_COLOR = discord.Color.from_str("#68ED7B")    # Success messages (green)
WARNING_COLOR = discord.Color.from_str("#EDC868")    # Warnings and cautions (yellow/orange)
GAME_COLOR = discord.Color.from_str("#68D4ED")       # Game-related embeds (cyan)
MATCHMAKING_COLOR = discord.Color.from_str("#B068ED") # Matchmaking/lobby embeds (purple)

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
    "codenames": ["games.CodenamesLite", "CodenamesLiteGame"],
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
    "codenames": {"sigma": 1 / 3, "beta": 1 / 6, "tau": 1 / 220, "draw": 0},
    "poker": {"sigma": 1 / 3, "beta": 1 / 6, "tau": 1 / 200, "draw": 0},
    "chess": {"sigma": 1 / 5, "beta": 1 / 10, "tau": 1 / 150, "draw": 1 / 10},
}

TEXTIFY_CURRENT_GAME_TURN = {
    "It's {player}'s turn to play.": 0.529,
    "Next up: {player}.": 0.45,
    "We checked the books, and it is *somehow* {player}'s turn to play. Not sure how that happened.": 0.01,
    "After journeying the Himalayas for many a year, we now know that it's {player}'s turn!": 0.01,
    "Did you know that the chance of this turn message appearing is 0.1%?. alsobythewayit's{player}'sturn": 0.001

}

# Textify options for game started messages
TEXTIFY_GAME_STARTED = {
    "The game has begun! Good luck, {players}!": 0.5,
    "Let the games begin! {players}, may the best player win!": 0.3,
    "Game on! {players} are ready to battle it out!": 0.15,
    "Alright {players}, let's see what you've got!": 0.04,
    "In a world where only one can win... {players} enter the arena.": 0.01,
}

# Textify options for join button text
TEXTIFY_BUTTON_JOIN = {
    "Join": 0.7,
    "Join Game": 0.2,
    "Count me in!": 0.08,
    "I'm in!": 0.02,
}

# Textify options for leave button text
TEXTIFY_BUTTON_LEAVE = {
    "Leave": 0.7,
    "Leave Game": 0.2,
    "Nah, I'm out": 0.08,
    "Goodbye!": 0.02,
}

# Textify options for start button text
TEXTIFY_BUTTON_START = {
    "Start": 0.7,
    "Start Game": 0.2,
    "Let's go!": 0.08,
    "Begin!": 0.02,
}

# Textify options for game over messages
TEXTIFY_GAME_OVER = {
    "Game over! {winner} wins!": 0.4,
    "And the winner is... {winner}!": 0.3,
    "Congratulations to {winner} for the victory!": 0.2,
    "{winner} has emerged victorious!": 0.08,
    "Against all odds, {winner} has won! What a game!": 0.02,
}

# Textify options for draw messages
TEXTIFY_GAME_DRAW = {
    "It's a draw!": 0.5,
    "The game ends in a tie!": 0.3,
    "No winner this time - it's a draw!": 0.15,
    "Both players are evenly matched! It's a tie!": 0.05,
}

SIGMA_RELATIVE_UNCERTAINTY_THRESHOLD = 0.20

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

DATABASE_GAME_IDS = {}

# Cross-server matchmaking queue
# Format: {game_type: {matchmaker_id: MatchmakingInterface}}
GLOBAL_MATCHMAKING_QUEUE = {}

# Whether to allow cross-server matchmaking (can be toggled)
CROSS_SERVER_MATCHMAKING_ENABLED = False

LONG_SPACE_EMBED = "\u2800"  # discord hides spaces when there is more than one in a row, this fixes it

# Button custom_id prefixes
BUTTON_PREFIX_JOIN = "join/"
BUTTON_PREFIX_LEAVE = "leave/"
BUTTON_PREFIX_START = "start/"
BUTTON_PREFIX_SELECT_CURRENT = "select_c/"
BUTTON_PREFIX_SELECT_NO_TURN = "select_n/"
BUTTON_PREFIX_CURRENT_TURN = "c/"
BUTTON_PREFIX_NO_TURN = "n/"
BUTTON_PREFIX_INVITE = "invite/"
BUTTON_PREFIX_SPECTATE = "spectate/"
BUTTON_PREFIX_PEEK = "peek/"

# Pagination button custom_id prefixes
BUTTON_PREFIX_PAGINATION = "pagination/"
BUTTON_PREFIX_PAGINATION_FIRST = "pagination_first/"
BUTTON_PREFIX_PAGINATION_PREV = "pagination_prev/"
BUTTON_PREFIX_PAGINATION_NEXT = "pagination_next/"
BUTTON_PREFIX_PAGINATION_LAST = "pagination_last/"

PRESENCE_TIMEOUT = 60
PRESENCE_PRESETS = [
    f"with {NAME}!",
    "games with friends!",
    "/play catalog"
]

# Permission and policy messages
PERMISSION_MSG_NOT_PARTICIPANT = "You are not a participant in this game."
PERMISSION_MSG_SPECTATE_DISABLED = "Spectating is disabled for this game."
PERMISSION_MSG_WRONG_CHANNEL = "This command can only be used in a game thread."
PERMISSION_MSG_NO_GAME_HERE = "There is no active game in this channel."
PERMISSION_MSG_NOT_YOUR_TURN = "It isn't your turn right now!"

# Thread policy settings
THREAD_POLICY_WARN_NON_PARTICIPANTS = True  # Warn users who message in game threads without being participants
THREAD_POLICY_DELETE_NON_PARTICIPANT_MESSAGES = False  # Delete messages from non-participants (more aggressive)
THREAD_POLICY_WARNING_MESSAGE = "⚠️ This is an active game thread. Only game participants can send messages here."
