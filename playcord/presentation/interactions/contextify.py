"""Discord interaction context strings for logging and diagnostics."""

from __future__ import annotations

import discord


def contextify(ctx: discord.Interaction | discord.Member) -> str:
    """Return a string with guild/user/interaction details for log lines and analytics.
    """
    is_guild_command = ctx.guild is not None
    guild_id = ctx.guild.id if is_guild_command else None
    guild_name = ctx.guild.name if is_guild_command else None

    if isinstance(ctx, discord.Interaction):
        return (
            f"guild_id={guild_id} guild_name={guild_name!r} user_id={ctx.user.id}, "
            f"user_name={ctx.user.name}, is_bot={ctx.user.bot}, data={ctx.data}, "
            f"type={ctx.type!r}"
        )
    if isinstance(ctx, discord.Member):
        return (
            f"guild_id={guild_id} guild_name={guild_name!r} user_id={ctx.user.id}, "
            f"user_name={ctx.user.name}, is_bot={ctx.user.bot}, nick={ctx.nick!r}"
        )
    return repr(ctx)
