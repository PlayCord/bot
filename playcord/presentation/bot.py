"""Refactored bot entrypoint."""

from __future__ import annotations

import sys

import discord
from discord import app_commands
from discord.app_commands.models import AppCommand, AppCommandGroup, Argument
from discord.ext import commands

from playcord.application.container import ApplicationContainer
from playcord.application.runtime_context import bind_application_container
from playcord.infrastructure import Translator, load_settings
from playcord.infrastructure.analytics_client import Timer
from playcord.infrastructure.config import bind_settings
from playcord.infrastructure.constants import (
    EPHEMERAL_DELETE_AFTER,
    bind_locale_strings,
)
from playcord.infrastructure.database import MigrationRunner, PoolManager
from playcord.infrastructure.logging import configure_logging, get_logger
from playcord.infrastructure.state.user_games import SessionRegistry
from playcord.presentation.cogs.general import GeneralCog
from playcord.presentation.interactions.command_tree_sync import build_tree
from playcord.presentation.interactions.error import command_error
from playcord.presentation.interactions.permissions import (
    STATIC_OWNER_IDS,
    resolve_effective_owner_ids,
)

log = get_logger()
startup_log = log.getChild("startup")


def _collect_remote_command_mentions(ac: AppCommand) -> dict[str, str]:
    mentions: dict[str, str] = {}

    def walk(node: AppCommand | AppCommandGroup, parts: tuple[str, ...]) -> None:
        options = list(getattr(node, "options", None) or [])
        mention = getattr(node, "mention", None)
        if not options or all(isinstance(opt, Argument) for opt in options):
            if mention:
                mentions[" ".join(parts)] = mention
            return
        for option in options:
            if (
                isinstance(opt := option, AppCommandGroup)
                or getattr(opt, "options", None) is not None
            ):
                walk(opt, (*parts, opt.name))

    walk(ac, (ac.name,))
    return mentions


class PlayCordBot(commands.Bot):
    """Thin presentation-layer bot."""

    def __init__(self, container: ApplicationContainer) -> None:
        super().__init__(
            command_prefix="!",
            intents=discord.Intents.all(),
            help_command=None,
        )
        self.container = container
        self._effective_owner_ids: frozenset[int] | None = None

    @property
    def effective_owner_ids(self) -> frozenset[int]:
        if self._effective_owner_ids is not None:
            return self._effective_owner_ids
        return STATIC_OWNER_IDS

    async def setup_hook(self) -> None:
        self._effective_owner_ids = await resolve_effective_owner_ids(self)

        await self.load_extension("playcord.presentation.cogs.general")
        await self.load_extension("playcord.presentation.cogs.matchmaking")
        await self.load_extension("playcord.presentation.cogs.games")
        await self.load_extension("playcord.presentation.cogs.events")
        await self.load_extension("playcord.presentation.cogs.admin")

        translator = self.container.translator

        async def _on_tree_error(
            interaction: discord.Interaction,
            error: app_commands.AppCommandError,
        ) -> None:
            await command_error(
                interaction,
                error,
                translator=translator,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )

        self.tree.on_error = _on_tree_error

        build_tree(self)

        general_cog = self.get_cog("GeneralCog")
        if isinstance(general_cog, GeneralCog) and not any(
            command.name == general_cog.command_root.name
            for command in self.tree.get_commands()
        ):
            self.tree.add_command(general_cog.command_root)

        await self._maybe_sync_commands_if_configured()
        await self._maybe_compare_command_tree_to_api()
        await self._refresh_command_mentions()

    async def _maybe_sync_commands_if_configured(self) -> None:
        if not self.container.settings.bot.auto_sync_commands:
            return
        try:
            synced = await self.tree.sync()
            startup_log.info("Auto-synced %d command(s).", len(synced))
        except Exception:
            startup_log.exception("Failed to auto-sync commands")

    async def _maybe_compare_command_tree_to_api(self) -> None:
        if not self.container.settings.bot.compare_command_tree_on_startup:
            return
        try:
            from playcord.presentation.interactions.command_tree_sync import (
                fetch_and_analyze_tree,
                format_drift_report,
            )

            drift = await fetch_and_analyze_tree(self.tree, guild=None)
            if drift["added"] or drift["removed"] or drift["modified"]:
                startup_log.warning(
                    "Command tree drift detected.\n%s",
                    format_drift_report(drift, max_lines=35),
                )
            else:
                startup_log.info("Command tree matches Discord API state.")
        except Exception:
            startup_log.exception("Failed to compare command tree to the API")

    async def _refresh_command_mentions(self) -> None:
        try:
            remote_commands = await self.tree.fetch_commands()
        except Exception:
            startup_log.exception(
                "Could not fetch slash commands for locale mention tokens",
            )
            self.container.translator.set_command_mentions(None)
            return

        mentions: dict[str, str] = {}
        for command in remote_commands:
            mentions.update(_collect_remote_command_mentions(command))
        self.container.translator.set_command_mentions(mentions)
        startup_log.info("Loaded %d slash command mention token(s).", len(mentions))


def create_container() -> ApplicationContainer:
    settings = load_settings()
    bind_settings(settings)
    configure_logging(settings.logging.level)
    translator = Translator(current_locale=settings.locale)
    bind_locale_strings(translator)
    pool_manager = PoolManager(settings.db)
    migration_runner = MigrationRunner(
        analytics_retention_days=settings.analytics_retention_days,
    )
    registry = SessionRegistry()
    container = ApplicationContainer(
        settings=settings,
        translator=translator,
        pool_manager=pool_manager,
        migration_runner=migration_runner,
        registry=registry,
    )

    bind_application_container(container)
    return container


def main() -> None:
    configure_logging("INFO")
    startup_timer = Timer().start()
    try:
        container = create_container()
    except Exception:
        startup_log.exception("Failed to create PlayCord application container")
        sys.exit(1)

    startup_log.info("Starting PlayCord after %sms", startup_timer.current_time)
    bot = PlayCordBot(container)
    bot.run(container.settings.bot.secret, log_handler=None)


if __name__ == "__main__":
    main()
