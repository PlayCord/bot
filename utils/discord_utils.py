import logging
import traceback

import discord
from discord import app_commands
from discord.app_commands import CheckFailure

from configuration.constants import IS_ACTIVE, LOGGING_ROOT
from utils.conversion import contextify
from utils.database import DatabaseConnectionError
from utils.locale import fmt, get, get_error
from utils import embeds as _embeds

CustomEmbed = _embeds.CustomEmbed
ErrorEmbed = _embeds.ErrorEmbed
UserErrorEmbed = getattr(_embeds, "UserErrorEmbed", ErrorEmbed)

log = logging.getLogger(LOGGING_ROOT)


def get_user_error_embed(error_key: str, **kwargs) -> UserErrorEmbed:
    """Get a pre-defined user error embed with optional formatting from locale."""
    title, description, suggestion = get_error(error_key)

    # Apply any formatting kwargs
    if kwargs:
        title = title.format(**kwargs)
        description = description.format(**kwargs)
        suggestion = suggestion.format(**kwargs)

    return UserErrorEmbed(title=title, description=description, suggestion=suggestion)


async def send_simple_embed(ctx: discord.Interaction, title: str, description: str, ephemeral: bool = True,
                            responded: bool = False) -> None:
    """
    Generate a simple embed
    """
    if not responded:
        await ctx.response.send_message(embed=CustomEmbed(title=title, description=description), ephemeral=ephemeral)
    else:
        await ctx.followup.send(embed=CustomEmbed(title=title, description=description), ephemeral=ephemeral)


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
    f_log.warning(f"Exception in command: {error} {contextify(ctx)}")

    if isinstance(error, CheckFailure):
        return

    # Check for database connection error - use friendly message
    if isinstance(error, app_commands.CommandInvokeError) and isinstance(error.original, DatabaseConnectionError):
        embed = get_user_error_embed("database_error")
        if ctx.response.is_done():
            await ctx.followup.send(embed=embed, ephemeral=True)
        else:
            await ctx.response.send_message(embed=embed, ephemeral=True)
        return

    # For unexpected errors, show the full error embed for debugging
    error_message = f"While running the command {ctx.command.name!r}, there was an error {error!r}"

    if ctx.response.is_done():
        try:
            await ctx.delete_original_response()
        except:
            pass
        await ctx.followup.send(embed=ErrorEmbed(ctx=ctx, what_failed=error_message, reason=traceback.format_exc()),
                                ephemeral=True)
    else:
        await ctx.response.send_message(
            embed=ErrorEmbed(ctx=ctx, what_failed=error_message, reason=traceback.format_exc()), ephemeral=True)


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
