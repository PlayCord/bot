import logging
import os
import sys

from discord import app_commands
from discord.ext import commands
from ruamel.yaml import YAML

import configuration.constants as constants
from cogs.games import handle_autocomplete, handle_move  # For exec context
from cogs.general import command_play
from configuration.constants import *
from utils import database as db
from utils.analytics import Timer
from utils.locale import fmt, get
from utils.command_builder import build_function_definitions
from utils.discord_utils import command_error
from utils.formatter import Formatter

# Logging setup
logging.getLogger("discord").setLevel(logging.INFO)
logging.basicConfig(level=logging.INFO)
root_logger = logging.getLogger("root")
root_logger.setLevel(logging.INFO)
ch = logging.StreamHandler(stream=sys.stdout)
ch.setLevel(logging.INFO)
ch.setFormatter(Formatter())
root_logger.handlers = [ch]

log = logging.getLogger(LOGGING_ROOT)
startup_logger = log.getChild("startup")

startup_logger.info(f"Welcome to {NAME} by @quantumbagel!")
startup_initial_time = Timer().start()


def load_configuration() -> dict | None:
    begin_load_config = Timer().start()
    try:
        with open(CONFIG_FILE) as config_file:
            loaded_config_file = YAML().load(config_file)
    except FileNotFoundError:
        startup_logger.critical("Configuration file not found.")
        return
    startup_logger.debug(f"Successfully loaded configuration file in {begin_load_config.current_time}ms!")
    return loaded_config_file


def apply_environment_overrides(config: dict) -> dict:
    """Override config values from environment for containerized deployments."""
    db_config = config.setdefault("db", {})

    direct_overrides = {
        "PLAYCORD_DB_TYPE": "type",
        "PLAYCORD_DB_HOST": "host",
        "PLAYCORD_DB_USER": "user",
        "PLAYCORD_DB_PASSWORD": "password",
        "PLAYCORD_DB_NAME": "database",
    }
    for env_key, config_key in direct_overrides.items():
        value = os.getenv(env_key)
        if value:
            db_config[config_key] = value

    int_overrides = {
        "PLAYCORD_DB_PORT": "port",
        "PLAYCORD_DB_POOL_SIZE": "pool_size",
        "PLAYCORD_DB_MAX_OVERFLOW": "max_overflow",
        "PLAYCORD_DB_POOL_TIMEOUT": "pool_timeout",
    }
    for env_key, config_key in int_overrides.items():
        value = os.getenv(env_key)
        if value:
            try:
                db_config[config_key] = int(value)
            except ValueError:
                startup_logger.warning(
                    f"Ignoring invalid integer for {env_key}: {value!r}"
                )

    return config


config = load_configuration()
if config is None:
    sys.exit(1)
config = apply_environment_overrides(config)
constants.CONFIGURATION = config

database_startup_time = Timer().start()
if not db.startup():
    startup_logger.critical("Database failed to connect on startup!")
    sys.exit(1)
else:
    startup_logger.info(f"Database startup completed in {database_startup_time.current_time}ms.")


class PlayCordBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all(), help_command=None)

    async def setup_hook(self):
        # Load Cogs
        await self.load_extension("cogs.general")
        await self.load_extension("cogs.matchmaking")
        await self.load_extension("cogs.games")
        await self.load_extension("cogs.events")
        await self.load_extension("cogs.admin")

        # Set up tree error handler
        self.tree.on_error = command_error

        # Dynamic command registration
        self.tree.add_command(command_play)
        dynamic_commands = build_function_definitions()

        for group in dynamic_commands:
            self.tree.add_command(group)

            # Shared globals for all commands in this group (so autocomplete callbacks can be found)
            group_exec_globals = {
                'discord': discord,
                'app_commands': app_commands,
                'group': group,
                'handle_move': handle_move,
                'handle_autocomplete': handle_autocomplete,
            }

            for command_str in dynamic_commands[group]:
                try:
                    exec(command_str, group_exec_globals)
                except Exception as e:
                    startup_logger.error(f"Failed to register dynamic command:\n{command_str}\nError: {e}")

        # Add command_root group from GeneralCog manually as it is not built dynamically
        general_cog = self.get_cog("GeneralCog")
        if general_cog:
            if not any(c.name == general_cog.command_root.name for c in self.tree.get_commands()):
                self.tree.add_command(general_cog.command_root)

        await self._maybe_sync_commands_if_configured()
        await self._maybe_compare_command_tree_to_api()

    async def _maybe_sync_commands_if_configured(self) -> None:
        """Optional: sync app command tree when config bot.auto_sync_commands is true."""
        cfg = constants.CONFIGURATION.get("bot", {}) or {}
        if not cfg.get("auto_sync_commands"):
            return
        try:
            synced = await self.tree.sync()
            startup_logger.info(
                fmt("startup.auto_sync_commands_ok", count=len(synced))
            )
        except Exception as e:
            startup_logger.warning(
                fmt("startup.auto_sync_commands_failed", error=str(e))
            )

    async def _maybe_compare_command_tree_to_api(self) -> None:
        """When bot.compare_command_tree_on_startup is true, log drift vs Discord (global tree)."""
        cfg = constants.CONFIGURATION.get("bot", {}) or {}
        if not cfg.get("compare_command_tree_on_startup"):
            return
        try:
            from utils.command_tree_diff import fetch_and_analyze_tree, format_drift_report

            drift = await fetch_and_analyze_tree(self.tree, guild=None)
            if drift["added"] or drift["removed"] or drift["modified"]:
                startup_logger.warning(
                    get("startup.compare_command_tree_drift_intro")
                    + "\n"
                    + format_drift_report(drift, max_lines=35)
                )
            else:
                startup_logger.info(get("startup.compare_command_tree_ok"))
        except Exception as e:
            startup_logger.warning(
                fmt("startup.compare_command_tree_failed", error=str(e))
            )


if __name__ == "__main__":
    bot = PlayCordBot()
    startup_logger.info(f"Starting bot after {startup_initial_time.current_time}ms")
    bot.run(config[CONFIG_BOT_SECRET], log_handler=None)
