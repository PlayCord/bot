import logging
import traceback

import discord
from discord import app_commands
from discord.app_commands import CheckFailure

from configuration.constants import IS_ACTIVE, LOGGING_ROOT, NAME
from utils.conversion import contextify
from utils.database import DatabaseConnectionError
from utils.embeds import CustomEmbed, ErrorEmbed

log = logging.getLogger(LOGGING_ROOT)


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
        await send_simple_embed(ctx, "Bot has been disabled!", f"{NAME} has been temporarily disabled.")
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

    # Check for database connection error
    if isinstance(error, app_commands.CommandInvokeError) and isinstance(error.original, DatabaseConnectionError):
        error_message = "The bot is currently unable to connect to its database. Please try again later."
    else:
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
