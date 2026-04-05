import logging
import discord
from discord import app_commands
from discord.app_commands import CheckFailure

from configuration.constants import IS_ACTIVE, LOGGING_ROOT
from utils.conversion import contextify
from utils.database import DatabaseConnectionError
from utils.locale import fmt, get, get_error
from utils import embeds as _embeds

ErrorEmbed = _embeds.ErrorEmbed
UserErrorEmbed = getattr(_embeds, "UserErrorEmbed", ErrorEmbed)

log = logging.getLogger(LOGGING_ROOT)


def format_user_error_message(error_key: str, **kwargs) -> str:
    """Plain-text user error for ephemeral replies: description + optional suggestion (no title)."""
    description, suggestion = get_error(error_key)
    if kwargs:
        description = description.format(**kwargs)
        if suggestion:
            suggestion = suggestion.format(**kwargs)
    parts = [p for p in (description, suggestion) if p]
    return "\n\n".join(parts)


def get_user_error_embed(error_key: str, **kwargs) -> UserErrorEmbed:
    """Get a pre-defined user error embed with optional formatting from locale (no title row)."""
    description, suggestion = get_error(error_key)

    if kwargs:
        description = description.format(**kwargs)
        if suggestion:
            suggestion = suggestion.format(**kwargs)

    return UserErrorEmbed(description=description, suggestion=suggestion or None)


async def send_simple_embed(ctx: discord.Interaction, title: str, description: str, ephemeral: bool = True,
                            responded: bool = False) -> None:
    """Send a short ephemeral status as plain text."""
    text = f"{title}\n{description}" if description else title
    if not responded:
        await ctx.response.send_message(content=text, ephemeral=ephemeral)
    else:
        await ctx.followup.send(content=text, ephemeral=ephemeral)


async def interaction_check(ctx: discord.Interaction) -> bool:
    f_log = log.getChild("is_allowed")

    if not IS_ACTIVE:
        await send_simple_embed(ctx,
                                fmt("bot.disabled_title"),
                                fmt("bot.disabled_description", name=get("brand.name")))
        f_log.warning("Interaction attempted when bot was disabled. " + contextify(ctx))
        return False

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
            await ctx.followup.send(content=msg, ephemeral=True)
        else:
            await ctx.response.send_message(content=msg, ephemeral=True)
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
        await ctx.followup.send(
            embed=ErrorEmbed(
                ctx=ctx,
                what_failed=get("system_error.command_unexpected"),
                reason=None,
            ),
            ephemeral=True,
        )
    else:
        await ctx.response.send_message(
            embed=ErrorEmbed(
                ctx=ctx,
                what_failed=get("system_error.command_unexpected"),
                reason=None,
            ),
            ephemeral=True,
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
