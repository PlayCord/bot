import logging
import traceback

import discord
from discord import app_commands
from discord.app_commands import CheckFailure

from configuration.constants import IS_ACTIVE, LOGGING_ROOT, NAME
from utils.conversion import contextify
from utils.database import DatabaseConnectionError
from utils.embeds import CustomEmbed, ErrorEmbed, UserErrorEmbed, WarningEmbed

log = logging.getLogger(LOGGING_ROOT)


# Common error messages with helpful guidance
ERROR_MESSAGES = {
    "not_in_matchmaking": {
        "title": "Not in a Lobby",
        "description": "You need to be in a game lobby to use this command.",
        "suggestion": "Start a new game with `/play <game>` or join an existing lobby first."
    },
    "not_creator": {
        "title": "Permission Denied",
        "description": "Only the lobby creator can perform this action.",
        "suggestion": "Ask the lobby creator to make changes, or create your own game lobby."
    },
    "already_in_game": {
        "title": "Already Playing",
        "description": "You're already in an active game.",
        "suggestion": "Finish your current game first, or forfeit it if you want to leave."
    },
    "user_not_found": {
        "title": "User Not Found",
        "description": "I couldn't find that user in this server.",
        "suggestion": "Make sure you're mentioning a valid user who is in this server."
    },
    "game_not_found": {
        "title": "Game Not Found",
        "description": "That game doesn't exist.",
        "suggestion": "Use `/playcord catalog` to see all available games."
    },
    "database_error": {
        "title": "Connection Issue",
        "description": "I'm having trouble connecting to the database right now.",
        "suggestion": "Please try again in a few moments. If this persists, the bot may be under maintenance."
    },
    "invalid_move": {
        "title": "Invalid Move",
        "description": "That move isn't allowed right now.",
        "suggestion": "Check the game rules or available moves and try again."
    },
    "not_your_turn": {
        "title": "Not Your Turn",
        "description": "It's not your turn to play.",
        "suggestion": "Wait for other players to make their moves."
    },
}


def get_user_error_embed(error_key: str, **kwargs) -> UserErrorEmbed:
    """Get a pre-defined user error embed with optional formatting."""
    if error_key not in ERROR_MESSAGES:
        return UserErrorEmbed(
            title="Something went wrong",
            description="An unexpected error occurred.",
            suggestion="Please try again. If the problem persists, use `/playcord help` for assistance."
        )
    
    error_info = ERROR_MESSAGES[error_key]
    title = error_info["title"].format(**kwargs) if kwargs else error_info["title"]
    description = error_info["description"].format(**kwargs) if kwargs else error_info["description"]
    suggestion = error_info["suggestion"].format(**kwargs) if kwargs else error_info["suggestion"]
    
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
