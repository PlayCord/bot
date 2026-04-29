"""Interaction guard helpers."""

from __future__ import annotations

import discord

from playcord.infrastructure.locale import Translator
from playcord.infrastructure.state.user_games import SessionRegistry
from playcord.presentation.interactions.respond import respond
from playcord.presentation.ui.views import UserErrorView


async def reject_bots(interaction: discord.Interaction) -> bool:
    return not bool(getattr(interaction.user, "bot", False))


async def active_thread_guard(
    interaction: discord.Interaction,
    *,
    registry: SessionRegistry,
    translator: Translator,
    command_group_name: str,
    allowed_command_name: str = "forfeit",
    delete_after: float = 10,
) -> bool:
    channel = getattr(interaction, "channel", None)
    command = getattr(interaction, "command", None)
    parent = getattr(command, "parent", None)

    in_active_game_thread = (
        channel is not None
        and getattr(channel, "type", None) == discord.ChannelType.private_thread
        and getattr(channel, "id", None) in registry.games_by_thread_id
    )
    is_group_subcommand = (
        parent is not None and getattr(parent, "name", None) == command_group_name
    )
    command_name = getattr(command, "name", None)

    if (
        in_active_game_thread
        and is_group_subcommand
        and command_name != allowed_command_name
    ):
        await respond(
            interaction,
            UserErrorView.create(
                translator.get("playcord.active_thread_command_restricted"),
                title="Not Available Here",
            ),
            ephemeral=True,
            delete_after=delete_after,
        )
        return False

    return True
