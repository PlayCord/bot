"""Shared response helpers for interactions."""

from __future__ import annotations

import asyncio
from typing import Any

import discord

from playcord.presentation.ui.view import View


def schedule_delete(message: Any, delay: float | None) -> None:
    if message is None or delay is None or delay <= 0:
        return

    async def _delete() -> None:
        try:
            await asyncio.sleep(delay)
            await message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

    try:
        asyncio.get_running_loop().create_task(_delete())
    except RuntimeError:
        return


async def respond(
    interaction: discord.Interaction,
    view: View | None = None,
    *,
    content: str | None = None,
    ephemeral: bool = False,
    delete_after: float | None = None,
) -> Any:
    payload = {"ephemeral": ephemeral}
    if view is not None:
        payload.update(view.to_send_kwargs())
    if content is not None:
        payload["content"] = content

    if interaction.response.is_done():
        message = await interaction.followup.send(**payload)
    else:
        message = await interaction.response.send_message(**payload)
    schedule_delete(message, delete_after)
    return message
