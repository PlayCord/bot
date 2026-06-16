"""
Static UX constants and locale-bound strings.

Populated via :func:`bind_locale_strings`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import discord

from playcord.games import GAMES

VERSION = "0.8.0"
NAME = ""
MANAGED_BY = ""
LOGGING_ROOT = "playcord"
MESSAGE_COMMAND_FAILED = "⛔"
MESSAGE_COMMAND_SUCCEEDED = "✅"
MESSAGE_COMMAND_PENDING = "⏳"
# Rebound from icon kit on emoji initialization when custom icons are uploaded.

MESSAGE_COMMAND_SYNC = "sync"
MESSAGE_COMMAND_CLEAR = "clear"
MESSAGE_COMMAND_ANALYTICS = "analytics"
MESSAGE_COMMAND_TREEDIFF = "treediff"
MESSAGE_COMMAND_DBRESET = "dbreset"
MESSAGE_COMMAND_EMOJI = "emoji"
MESSAGE_COMMAND_SPECIFY_LOCAL_SERVER = "this"

EMBED_COLOR = None
ERROR_COLOR = discord.Color.from_str("#ED6868")
INFO_COLOR = None
SUCCESS_COLOR = discord.Color.from_str("#68ED7B")
WARNING_COLOR = discord.Color.from_str("#EDC868")
GAME_COLOR = None
MATCHMAKING_COLOR = None

_CONFIG_ROOT = Path(__file__).resolve().parent.parent / "configuration"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = str(_CONFIG_ROOT / "config.yaml")
EMOJI_CONFIGURATION_FILE = str(_CONFIG_ROOT / "emoji.yaml")
ICONS_DIR = _PROJECT_ROOT / "assets" / "icons"

GAME_TYPES: dict[str, list[str]] = {
    game.key: [game.module_name, game.class_name] for game in GAMES
}

TEXTIFY_CURRENT_GAME_TURN: dict[str, Any] = {}
TEXTIFY_GAME_STARTED: dict[str, Any] = {}
TEXTIFY_BUTTON_JOIN: dict[str, Any] = {}
TEXTIFY_BUTTON_LEAVE: dict[str, Any] = {}
TEXTIFY_BUTTON_START: dict[str, Any] = {}
TEXTIFY_GAME_OVER: dict[str, Any] = {}
TEXTIFY_GAME_DRAW: dict[str, Any] = {}

LONG_SPACE_EMBED = "\u2800"

BUTTON_PREFIX_JOIN = "join/"
BUTTON_PREFIX_LEAVE = "leave/"
BUTTON_PREFIX_START = "start/"
BUTTON_PREFIX_READY = "ready/"
BUTTON_PREFIX_LOBBY_OPT = "lobbyopt/"
BUTTON_PREFIX_LOBBY_ROLE = "lobbyrole/"
BUTTON_PREFIX_LOBBY_ASSIGN_ROLES = "lobbyassign/"
BUTTON_PREFIX_LOBBY_SETTINGS = "lobbysettings/"
BUTTON_PREFIX_LOBBY_SETTINGS_PRIV = "lobbysetpriv/"
BUTTON_PREFIX_LOBBY_SETTINGS_RESET_PRIV = "lobbysetresetpriv/"
BUTTON_PREFIX_LOBBY_SETTINGS_RESET_RULES = "lobbysetresetrules/"
BUTTON_PREFIX_LOBBY_SETTINGS_END = "lobbysetend/"
BUTTON_PREFIX_SELECT_CURRENT = "select_c/"
BUTTON_PREFIX_SELECT_NO_TURN = "select_n/"
BUTTON_PREFIX_CURRENT_TURN = "c/"
BUTTON_PREFIX_NO_TURN = "n/"
BUTTON_PREFIX_GAME_MOVE = "game_move/"
BUTTON_PREFIX_GAME_SELECT = "game_select/"
BUTTON_PREFIX_INVITE = "invite/"
BUTTON_PREFIX_SPECTATE = "spectate/"
BUTTON_PREFIX_PEEK = "peek/"
BUTTON_PREFIX_REPLAY_NAV = "replay_nav/"
BUTTON_PREFIX_REPLAY_NOOP = "replay_noop/"
BUTTON_PREFIX_PAGINATION_FIRST = "pagination_first/"
BUTTON_PREFIX_PAGINATION_PREV = "pagination_prev/"
BUTTON_PREFIX_PAGINATION_PAGE = "pagination_page/"
BUTTON_PREFIX_PAGINATION_NEXT = "pagination_next/"
BUTTON_PREFIX_PAGINATION_LAST = "pagination_last/"
BUTTON_PREFIX_REMATCH = "rematch/"

PRESENCE_TIMEOUT = 60
EPHEMERAL_DELETE_AFTER = 10

ANALYTICS_PERIODIC_FLUSH_INITIAL_DELAY_SECONDS = 60
ANALYTICS_PERIODIC_FLUSH_INTERVAL_SECONDS = 120
# Retention DELETE runs at startup (migrations) and on this interval — not every flush tick.
ANALYTICS_PERIODIC_CLEANUP_INTERVAL_SECONDS = 86_400

HISTORY_PAGE_SIZE = 8
CATALOG_GAMES_PER_PAGE = 3

ERROR_IMPORTED = ""
ERROR_NO_SYSTEM_CHANNEL = ""
ERROR_INCORRECT_SETUP = ""

PERMISSION_MSG_NOT_PARTICIPANT = ""
PERMISSION_MSG_SPECTATE_DISABLED = ""
PERMISSION_MSG_WRONG_CHANNEL = ""
PERMISSION_MSG_NO_GAME_HERE = ""
PERMISSION_MSG_NOT_YOUR_TURN = ""

GAME_MSG_ALREADY_OVER = ""

THREAD_POLICY_WARN_NON_PARTICIPANTS = True
THREAD_POLICY_DELETE_NON_PARTICIPANT_MESSAGES = False
THREAD_POLICY_WARNING_MESSAGE = ""
THREAD_POLICY_PARTICIPANTS_COMMANDS_ONLY = False
THREAD_POLICY_SPECTATORS_SILENT = False


def bind_locale_strings() -> None:
    """Populate locale-backed module attributes (call once at startup)."""
    global NAME, MANAGED_BY, ERROR_IMPORTED
    global ERROR_NO_SYSTEM_CHANNEL, ERROR_INCORRECT_SETUP
    global TEXTIFY_CURRENT_GAME_TURN, TEXTIFY_GAME_STARTED, TEXTIFY_BUTTON_JOIN
    global TEXTIFY_BUTTON_LEAVE, TEXTIFY_BUTTON_START
    global TEXTIFY_GAME_OVER, TEXTIFY_GAME_DRAW
    global PERMISSION_MSG_NOT_PARTICIPANT, PERMISSION_MSG_SPECTATE_DISABLED
    global PERMISSION_MSG_WRONG_CHANNEL, PERMISSION_MSG_NO_GAME_HERE
    global PERMISSION_MSG_NOT_YOUR_TURN
    global GAME_MSG_ALREADY_OVER, THREAD_POLICY_WARNING_MESSAGE

    from playcord.infrastructure.locale import get, get_dict

    NAME = get("brand.name")
    MANAGED_BY = get("meta.author")
    ERROR_IMPORTED = get("errors.imported_wrong_entrypoint")
    ERROR_NO_SYSTEM_CHANNEL = get("errors.no_system_channel")
    ERROR_INCORRECT_SETUP = get("errors.incorrect_setup")
    TEXTIFY_CURRENT_GAME_TURN = get_dict("game.turn")
    TEXTIFY_GAME_STARTED = get_dict("game.started")
    TEXTIFY_BUTTON_JOIN = get_dict("buttons.textify.join")
    TEXTIFY_BUTTON_LEAVE = get_dict("buttons.textify.leave")
    TEXTIFY_BUTTON_START = get_dict("buttons.textify.start")
    TEXTIFY_GAME_OVER = get_dict("game.over")
    TEXTIFY_GAME_DRAW = get_dict("game.draw")
    PERMISSION_MSG_NOT_PARTICIPANT = get("permissions.not_participant")
    PERMISSION_MSG_SPECTATE_DISABLED = get("permissions.spectate_disabled")
    PERMISSION_MSG_WRONG_CHANNEL = get("permissions.wrong_channel")
    PERMISSION_MSG_NO_GAME_HERE = get("permissions.no_game_here")
    PERMISSION_MSG_NOT_YOUR_TURN = get("permissions.not_your_turn")
    GAME_MSG_ALREADY_OVER = get("game.errors.already_over")
    THREAD_POLICY_WARNING_MESSAGE = get("thread_policy.warning")
