from __future__ import annotations

import asyncio
import typing
from typing import Any

import discord
from discord.app_commands import Choice

from playcord.application.runtime_context import try_get_container
from playcord.infrastructure.constants import (
    EPHEMERAL_DELETE_AFTER,
    INFO_COLOR,
    LOGGING_ROOT,
)
from playcord.infrastructure.database.implementation.internal_player import (
    InternalPlayer,
)
from playcord.infrastructure.locale import get, get_error
from playcord.infrastructure.logging import get_logger
from playcord.presentation.ui.containers import (
    CustomContainer,
    UserErrorContainer,
    container_send_kwargs,
)

log = get_logger()


def _active_game_threads(
    ctx: discord.Interaction | None = None,
) -> dict[int, Any]:
    """Thread ids that currently host an active game (same backing store as SessionRegistry)."""
    if ctx is not None:
        c = getattr(getattr(ctx, "client", None), "container", None)
        if c is not None:
            return c.registry.games_by_thread_id
    bound = try_get_container()
    if bound is not None:
        return bound.registry.games_by_thread_id
    return {}


def schedule_ephemeral_message_delete(message: Any, delay: float | None) -> None:
    """Delete *message* after *delay* seconds (interaction
    webhooks often lack delete_after on send).
    """
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


async def followup_send(
    interaction: discord.Interaction, *args: Any, **kwargs: Any,
) -> Any:
    delay = kwargs.pop("delete_after", None)
    msg = await interaction.followup.send(*args, **kwargs)
    schedule_ephemeral_message_delete(msg, delay)
    return msg


async def response_send_message(
    interaction: discord.Interaction, *args: Any, **kwargs: Any,
) -> Any:
    delay = kwargs.pop("delete_after", None)
    msg = await interaction.response.send_message(*args, **kwargs)
    schedule_ephemeral_message_delete(msg, delay)
    return msg


def format_user_error_message(error_key: str, **kwargs) -> str:
    """Plain-text user error with a
    single combined sentence block (no title/container).
    """
    message = get_error(error_key)
    if not message:
        return f"{error_key}"
    if kwargs:
        try:
            message = message.format(**kwargs)
        except KeyError as e:
            log.warning("Missing format variable %r for error key '%s'", e, error_key)
    return str(message).strip()


def get_user_error_embed(error_key: str, **kwargs) -> UserErrorContainer:
    """Get a pre-defined user error container with
    optional formatting from locale (no title row).
    """
    message = get_error(error_key)
    if not message:
        message = get("errors.generic")
    if kwargs:
        try:
            message = message.format(**kwargs)
        except KeyError as e:
            log.warning("Missing format variable %r for error key '%s'", e, error_key)

    return UserErrorContainer(description=message, suggestion=None)


async def send_simple_embed(
    ctx: discord.Interaction,
    title: str,
    description: str,
    ephemeral: bool = True,
    responded: bool = False,
) -> None:
    """Send a short status using the shared container UI."""
    card = CustomContainer(
        title=title, description=description or None, color=INFO_COLOR,
    )
    kwargs = {
        **container_send_kwargs(card),
        "ephemeral": ephemeral,
    }
    if not responded:
        await response_send_message(
            ctx, **kwargs, delete_after=EPHEMERAL_DELETE_AFTER if ephemeral else None,
        )
    else:
        await followup_send(
            ctx, **kwargs, delete_after=EPHEMERAL_DELETE_AFTER if ephemeral else None,
        )


async def interaction_check(ctx: discord.Interaction) -> bool:
    f_log = log.getChild("is_allowed")

    if ctx.user.bot:
        f_log.warning("Bot users are not allowed to use commands.")
        return False

    channel = getattr(ctx, "channel", None)
    in_active_game_thread = (
        channel is not None
        and getattr(channel, "type", None) == discord.ChannelType.private_thread
        and getattr(channel, "id", None) in _active_game_threads(ctx)
    )
    command = getattr(ctx, "command", None)
    parent = getattr(command, "parent", None)
    is_playcord_subcommand = (
        parent is not None and getattr(parent, "name", None) == LOGGING_ROOT
    )
    command_name = getattr(command, "name", None)
    if in_active_game_thread and is_playcord_subcommand and command_name != "forfeit":
        msg = get("playcord.active_thread_command_restricted")
        if ctx.response.is_done():
            await followup_send(
                ctx, content=msg, ephemeral=True, delete_after=EPHEMERAL_DELETE_AFTER,
            )
        else:
            await response_send_message(
                ctx, content=msg, ephemeral=True, delete_after=EPHEMERAL_DELETE_AFTER,
            )
        return False

    return True


def discord_user_db_label(user: discord.User | discord.Member) -> str | None:
    """Best-effort display string for persistence when only primitive IDs are passed."""
    disp = getattr(user, "display_name", None)
    if disp:
        return str(disp)
    name = getattr(user, "name", None)
    return str(name) if name else None


def shallow_player_from_discord_user(
    user: discord.User | discord.Member,
) -> InternalPlayer:
    """Build a rating-empty InternalPlayer from Discord identity (presentation-only)."""
    return InternalPlayer(
        ratings={},
        id=int(user.id),
        username=discord_user_db_label(user),
    )


def get_shallow_player(user: discord.User | discord.Member) -> InternalPlayer:
    """Compatibility name for :func:`shallow_player_from_discord_user`."""
    return shallow_player_from_discord_user(user)


async def decode_discord_arguments(argument: Choice | typing.Any) -> typing.Any:
    """Decode discord arguments from discord so they can be passed to the move function
    """
    if isinstance(argument, Choice):
        return argument.value
    return argument
