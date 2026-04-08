import asyncio
import logging
from typing import Any

import discord
from discord import app_commands
from discord.app_commands import CheckFailure

from configuration.constants import EPHEMERAL_DELETE_AFTER, INFO_COLOR, LOGGING_ROOT
from utils.containers import CustomContainer, ErrorContainer, UserErrorContainer, container_send_kwargs
from utils.conversion import contextify
from utils.database import DatabaseConnectionError
from utils.locale import fmt, get, get_error

log = logging.getLogger(LOGGING_ROOT)


def schedule_ephemeral_message_delete(message: Any, delay: float | None) -> None:
    """Delete *message* after *delay* seconds (interaction webhooks often lack delete_after on send)."""
    if message is None or delay is None or delay <= 0:
        return

    async def _run() -> None:
        try:
            await asyncio.sleep(delay)
            await message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        pass


async def followup_send(interaction: discord.Interaction, *args: Any, **kwargs: Any) -> Any:
    delay = kwargs.pop("delete_after", None)
    msg = await interaction.followup.send(*args, **kwargs)
    schedule_ephemeral_message_delete(msg, delay)
    return msg


async def response_send_message(interaction: discord.Interaction, *args: Any, **kwargs: Any) -> Any:
    delay = kwargs.pop("delete_after", None)
    msg = await interaction.response.send_message(*args, **kwargs)
    schedule_ephemeral_message_delete(msg, delay)
    return msg


def format_user_error_message(error_key: str, **kwargs) -> str:
    """Plain-text user error for ephemeral replies: description + optional suggestion (no title)."""
    description, suggestion = get_error(error_key)
    if kwargs:
        description = description.format(**kwargs)
        if suggestion:
            suggestion = suggestion.format(**kwargs)
    parts = [p for p in (description, suggestion) if p]
    return "\n\n".join(parts)


def get_user_error_embed(error_key: str, **kwargs) -> UserErrorContainer:
    """Get a pre-defined user error container with optional formatting from locale (no title row)."""
    description, suggestion = get_error(error_key)

    if kwargs:
        description = description.format(**kwargs)
        if suggestion:
            suggestion = suggestion.format(**kwargs)

    return UserErrorContainer(description=description, suggestion=suggestion or None)


async def send_simple_embed(ctx: discord.Interaction, title: str, description: str, ephemeral: bool = True,
                            responded: bool = False) -> None:
    """Send a short status using the shared container UI."""
    card = CustomContainer(title=title, description=description or None, color=INFO_COLOR)
    kwargs = {
        **container_send_kwargs(card),
        "ephemeral": ephemeral,
    }
    if not responded:
        await response_send_message(ctx, **kwargs, delete_after=EPHEMERAL_DELETE_AFTER if ephemeral else None)
    else:
        await followup_send(ctx, **kwargs, delete_after=EPHEMERAL_DELETE_AFTER if ephemeral else None)


async def interaction_check(ctx: discord.Interaction) -> bool:
    f_log = log.getChild("is_allowed")

    if ctx.user.bot:
        f_log.warning("Bot users are not allowed to use commands.")
        return False

    return True


async def command_error(ctx: discord.Interaction, error: app_commands.AppCommandError):
    f_log = log.getChild("error")

    if isinstance(error, CheckFailure):
        return

    # Check for database connection error - use friendly message
    if isinstance(error, app_commands.CommandInvokeError) and isinstance(error.original, DatabaseConnectionError):
        msg = format_user_error_message("database_error")
        if ctx.response.is_done():
            await followup_send(ctx, content=msg, ephemeral=True, delete_after=EPHEMERAL_DELETE_AFTER)
        else:
            await response_send_message(ctx, content=msg, ephemeral=True, delete_after=EPHEMERAL_DELETE_AFTER)
        return

    cmd_name = getattr(ctx.command, "name", None) or "unknown"
    if isinstance(error, app_commands.CommandInvokeError) and error.original:
        f_log.error(
            "Command failed (cmd=%r): %s",
            cmd_name,
            contextify(ctx),
            exc_info=error.original,
        )
    else:
        f_log.error("App command error (cmd=%r): %r %s", cmd_name, error, contextify(ctx))

    if ctx.response.is_done():
        try:
            await ctx.delete_original_response()
        except (discord.HTTPException, discord.NotFound):
            pass
        await followup_send(
            ctx,
            **container_send_kwargs(ErrorContainer(
                ctx=ctx,
                what_failed=get("system_error.command_unexpected"),
                reason=None,
            )),
            ephemeral=True,
            delete_after=EPHEMERAL_DELETE_AFTER,
        )
    else:
        await response_send_message(
            ctx,
            **container_send_kwargs(ErrorContainer(
                ctx=ctx,
                what_failed=get("system_error.command_unexpected"),
                reason=None,
            )),
            ephemeral=True,
            delete_after=EPHEMERAL_DELETE_AFTER,
        )


from discord.app_commands import Choice
import typing


async def decode_discord_arguments(argument: Choice | typing.Any) -> typing.Any:
    """
    Decode discord arguments from discord so they can be passed to the move function
    """
    if isinstance(argument, Choice):
        return argument.value
    else:
        return argument
