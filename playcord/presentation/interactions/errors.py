"""Unified interaction error handling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Type

import discord
from discord import app_commands
from discord.app_commands import CheckFailure

from playcord.application.errors import ApplicationError, ForbiddenError, NotFoundError
from playcord.domain.errors import DomainError
from playcord.infrastructure.locale import Translator
from playcord.infrastructure.logging import get_logger
from playcord.presentation.interactions.respond import respond
from playcord.presentation.ui.views import ErrorView, UserErrorView
from playcord.utils.database import DatabaseConnectionError

log = get_logger("presentation.errors")


@dataclass(frozen=True, slots=True)
class ErrorMapping:
    exception_type: Type[BaseException]
    locale_key: str
    title: str


ERROR_MAPPINGS = (
    ErrorMapping(DatabaseConnectionError, "errors.database_error", "Database Error"),
    ErrorMapping(ForbiddenError, "errors.generic", "Permission Denied"),
    ErrorMapping(NotFoundError, "errors.generic", "Not Found"),
    ErrorMapping(DomainError, "errors.generic", "Invalid Action"),
    ErrorMapping(ApplicationError, "errors.generic", "Application Error"),
)


async def command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
    *,
    translator: Translator,
    delete_after: float = 10,
) -> None:
    if isinstance(error, CheckFailure):
        return

    original = error.original if isinstance(error, app_commands.CommandInvokeError) else error

    for mapping in ERROR_MAPPINGS:
        if isinstance(original, mapping.exception_type):
            await respond(
                interaction,
                UserErrorView.create(
                    translator.get(mapping.locale_key, "[errors.generic]"),
                    title=mapping.title,
                ),
                ephemeral=True,
                delete_after=delete_after,
            )
            return

    log.exception(
        "Unhandled app command error for command=%r",
        getattr(interaction.command, "name", "unknown"),
        exc_info=original,
    )
    await respond(
        interaction,
        ErrorView.create(
            translator.get("errors.generic", "[errors.generic]"),
            title="Unexpected Error",
        ),
        ephemeral=True,
        delete_after=delete_after,
    )
