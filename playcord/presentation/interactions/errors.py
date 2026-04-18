"""Unified interaction error handling."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.app_commands import CheckFailure

from playcord.infrastructure.locale import Translator
from playcord.presentation.interactions.error_reporter import ErrorSurface, report


async def command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
    *,
    translator: Translator,
    delete_after: float = 10,
) -> None:
    if isinstance(error, CheckFailure):
        return

    await report(
        interaction,
        error,
        surface=ErrorSurface.SLASH,
        translator=translator,
        delete_after=delete_after,
    )
