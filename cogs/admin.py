import asyncio
import logging
import traceback

import discord
from discord.ext import commands

from configuration.constants import *
from utils import database as db
from utils.analytics import format_recent_event_row, render_analytics_matplotlib_summary
from utils.embeds import ErrorEmbed, append_chunked_fields, lines_to_embed_field_chunks
from utils.locale import fmt, get

log = logging.getLogger(LOGGING_ROOT)


async def _add_processing_reaction(msg: discord.Message) -> None:
    try:
        await msg.add_reaction(MESSAGE_COMMAND_PENDING)
    except discord.HTTPException:
        pass


async def _finalize_admin_reactions(
    msg: discord.Message, bot_user: discord.abc.User, *, success: bool
) -> None:
    try:
        await msg.remove_reaction(MESSAGE_COMMAND_PENDING, bot_user)
    except discord.HTTPException:
        pass
    emoji = MESSAGE_COMMAND_SUCCEEDED if success else MESSAGE_COMMAND_FAILED
    try:
        await msg.add_reaction(emoji)
    except discord.HTTPException:
        pass


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _run_long_admin_task(self, msg: discord.Message, work) -> None:
        """Add ⏳, await ``work(msg) -> bool``, then replace with ✅ or ⛔."""
        await _add_processing_reaction(msg)
        ok = False
        try:
            ok = await work(msg)
        except Exception:
            log.exception("Owner admin message task failed")
            try:
                await msg.reply(
                    embed=ErrorEmbed(
                        what_failed=get("commands.admin.task_unexpected_error"),
                        reason=traceback.format_exc(),
                    )
                )
            except discord.HTTPException:
                pass
            ok = False
        finally:
            await _finalize_admin_reactions(msg, self.bot.user, success=ok)

    def _spawn_long_admin_task(self, msg: discord.Message, work) -> None:
        asyncio.create_task(self._run_long_admin_task(msg, work))

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message) -> None:
        """
        Handle message commands for bot administration
        """
        if msg.author.bot or msg.author.id not in OWNERS:
            return

        f_log = log.getChild("event.on_message")

        if msg.content.startswith(f"{LOGGING_ROOT}/"):
            f_log.info(f"Received authorized message command {msg.content!r}.")

        # Sync (Discord API — can be slow)
        if msg.content.startswith(f"{LOGGING_ROOT}/{MESSAGE_COMMAND_SYNC}"):
            self._spawn_long_admin_task(msg, self._task_sync)

        # Disable
        elif msg.content == f"{LOGGING_ROOT}/{MESSAGE_COMMAND_DISABLE}":
            import configuration.constants as constants
            if not constants.IS_ACTIVE:
                await msg.add_reaction(MESSAGE_COMMAND_FAILED)
                return
            constants.IS_ACTIVE = False
            f_log.critical(f"Bot has been disabled by authorized user {msg.author.id}.")
            await msg.add_reaction(MESSAGE_COMMAND_SUCCEEDED)

        # Enable
        elif msg.content == f"{LOGGING_ROOT}/{MESSAGE_COMMAND_ENABLE}":
            import configuration.constants as constants
            if constants.IS_ACTIVE:
                await msg.add_reaction(MESSAGE_COMMAND_FAILED)
                return
            constants.IS_ACTIVE = True
            f_log.critical(f"Bot has been enabled by authorized user {msg.author.id}.")
            await msg.add_reaction(MESSAGE_COMMAND_SUCCEEDED)

        # Toggle
        elif msg.content == f"{LOGGING_ROOT}/{MESSAGE_COMMAND_TOGGLE}":
            import configuration.constants as constants
            constants.IS_ACTIVE = not constants.IS_ACTIVE
            f_log.critical(
                f"Bot has been {'enabled' if constants.IS_ACTIVE else 'disabled'} by authorized user {msg.author.id}.")
            await msg.add_reaction(MESSAGE_COMMAND_SUCCEEDED)

        # Analytics — owner message `playcord/analytics [hours]` (DB + matplotlib)
        elif msg.content.startswith(f"{LOGGING_ROOT}/{MESSAGE_COMMAND_ANALYTICS}"):
            self._spawn_long_admin_task(msg, self._task_analytics)

        # Slash tree deep diff
        elif msg.content.startswith(f"{LOGGING_ROOT}/{MESSAGE_COMMAND_TREEDIFF}"):
            self._spawn_long_admin_task(msg, self._task_treediff)

        # Clear (tree sync — can be slow)
        elif msg.content.startswith(f"{LOGGING_ROOT}/{MESSAGE_COMMAND_CLEAR}"):
            self._spawn_long_admin_task(msg, self._task_clear)

        # Database reset helpers
        elif msg.content.startswith(f"{LOGGING_ROOT}/{MESSAGE_COMMAND_DBRESET}"):
            self._spawn_long_admin_task(msg, self._task_dbreset)

    async def _task_sync(self, msg: discord.Message) -> bool:
        f_log = log.getChild("event.on_message")
        split = msg.content.split()
        if len(split) == 1:
            try:
                await self.bot.tree.sync()
            except Exception as e:
                await msg.reply(
                    embed=ErrorEmbed(
                        what_failed=fmt(
                            "commands.admin.sync_failed",
                            error_type=type(e).__name__,
                        ),
                        reason=traceback.format_exc(),
                    )
                )
                return False
            f_log.info(f"Performed authorized sync from user {msg.author.id} to all guilds.")
            return True

        if split[1] == MESSAGE_COMMAND_SPECIFY_LOCAL_SERVER:
            if msg.guild is None:
                await msg.reply(get("commands.admin.guild_required_for_this"))
                return False
            g = msg.guild
        else:
            try:
                g = discord.Object(id=int(split[1]))
            except ValueError:
                await msg.reply(fmt("commands.admin.sync_usage", prefix=f"{LOGGING_ROOT}/"))
                return False

        self.bot.tree.copy_global_to(guild=g)
        try:
            await self.bot.tree.sync(guild=g)
        except Exception as e:
            await msg.reply(
                embed=ErrorEmbed(
                    what_failed=fmt(
                        "commands.admin.sync_failed",
                        error_type=type(e).__name__,
                    ),
                    reason=traceback.format_exc(),
                )
            )
            return False
        f_log.info(f"Performed authorized sync from user {msg.author.id} to guild {g.id}")
        return True

    async def _task_analytics(self, msg: discord.Message) -> bool:
        split = msg.content.split()
        hours = 24
        if len(split) >= 2:
            try:
                hours = int(split[1])
            except ValueError:
                await msg.reply(
                    embed=discord.Embed(
                        description=fmt(
                            "commands.analytics.message_usage",
                            prefix=f"{LOGGING_ROOT}/",
                        ),
                        color=INFO_COLOR,
                    )
                )
                return False
        hours = max(1, min(hours, 24 * 30))
        counts = db.database.get_analytics_event_counts(hours=hours)
        by_game = db.database.get_analytics_event_counts_by_game(hours=hours)
        recent = db.database.get_analytics_recent_events(hours=hours, limit=60)
        if not counts and not recent and not by_game:
            await msg.reply(
                embed=discord.Embed(
                    title=fmt("commands.analytics.embed_title", hours=hours),
                    description=fmt("commands.analytics.message_empty", hours=hours),
                    color=EMBED_COLOR,
                )
            )
            return True

        chart_buf = await asyncio.to_thread(
            render_analytics_matplotlib_summary, counts, by_game, hours
        )
        main_embed = discord.Embed(
            title=fmt("commands.analytics.embed_title", hours=hours),
            description=(
                get("commands.analytics.embed_description")
                if chart_buf is not None
                else get("commands.analytics.embed_no_chart")
            ),
            color=EMBED_COLOR,
        )
        if chart_buf is not None:
            chart_buf.seek(0)
            main_embed.set_image(url="attachment://playcord-analytics.png")

        recent_lines: list[str] = (
            [format_recent_event_row(r) for r in recent]
            if recent
            else [get("common.empty_markdown")]
        )
        append_chunked_fields(
            main_embed,
            lines_to_embed_field_chunks(recent_lines),
            first_name=get("commands.analytics.field_recent"),
            truncated_note=get("commands.analytics.recent_truncated_note"),
        )

        if chart_buf is not None:
            await msg.reply(
                embed=main_embed,
                file=discord.File(chart_buf, filename="playcord-analytics.png"),
            )
        else:
            await msg.reply(embed=main_embed)
        return True

    async def _task_treediff(self, msg: discord.Message) -> bool:
        split = msg.content.split()
        guild: discord.Guild | discord.Object | None = None
        if len(split) >= 2:
            if split[1] == MESSAGE_COMMAND_SPECIFY_LOCAL_SERVER:
                if msg.guild is None:
                    await msg.reply(
                        embed=discord.Embed(
                            description=get("commands.treediff.need_guild"),
                            color=WARNING_COLOR,
                        )
                    )
                    return False
                guild = msg.guild
            else:
                try:
                    guild = discord.Object(id=int(split[1]))
                except ValueError:
                    await msg.reply(
                        embed=discord.Embed(
                            description=fmt(
                                "commands.treediff.message_usage",
                                prefix=f"{LOGGING_ROOT}/",
                            ),
                            color=INFO_COLOR,
                        )
                    )
                    return False
        try:
            from utils.command_tree_diff import drift_to_embed, fetch_and_analyze_tree

            drift = await fetch_and_analyze_tree(self.bot.tree, guild=guild)
        except discord.HTTPException as e:
            await msg.reply(
                embed=ErrorEmbed(
                    what_failed=get("commands.treediff.message_failed"),
                    reason=str(e),
                )
            )
            return False
        except Exception:
            await msg.reply(
                embed=ErrorEmbed(
                    what_failed=get("commands.treediff.message_failed"),
                    reason=traceback.format_exc(),
                )
            )
            return False
        diff_embed = drift_to_embed(
            drift,
            color=EMBED_COLOR,
            title=get("commands.treediff.embed_title"),
        )
        await msg.reply(embed=diff_embed)
        return True

    async def _task_clear(self, msg: discord.Message) -> bool:
        f_log = log.getChild("event.on_message")
        split = msg.content.split()
        if len(split) == 1:
            self.bot.tree.clear_commands(guild=None)
            await self.bot.tree.sync()
            f_log.info(f"Performed authorized command tree clear from user {msg.author.id} to all guilds.")
            return True

        if split[1] == MESSAGE_COMMAND_SPECIFY_LOCAL_SERVER:
            if msg.guild is None:
                await msg.reply(get("commands.admin.guild_required_for_this"))
                return False
            g = msg.guild
        else:
            try:
                g = discord.Object(id=int(split[1]))
            except ValueError:
                await msg.reply(fmt("commands.admin.clear_usage", prefix=f"{LOGGING_ROOT}/"))
                return False
        self.bot.tree.clear_commands(guild=g)
        await self.bot.tree.sync(guild=g)
        f_log.info(f"Performed authorized command tree clear from user {msg.author.id} to guild {g.id}")
        return True

    async def _task_dbreset(self, msg: discord.Message) -> bool:
        split = msg.content.split()
        usage = (
            f"`{LOGGING_ROOT}/{MESSAGE_COMMAND_DBRESET} game <id>`\n"
            f"`{LOGGING_ROOT}/{MESSAGE_COMMAND_DBRESET} all`\n"
            f"`{LOGGING_ROOT}/{MESSAGE_COMMAND_DBRESET} user <id>`\n"
            f"`{LOGGING_ROOT}/{MESSAGE_COMMAND_DBRESET} guild <id|{MESSAGE_COMMAND_SPECIFY_LOCAL_SERVER}>`"
        )
        if len(split) < 2:
            await msg.reply(embed=discord.Embed(description=usage, color=INFO_COLOR))
            return False

        target = split[1].lower()
        if target == "all":
            if len(split) != 2:
                await msg.reply(embed=discord.Embed(description=usage, color=INFO_COLOR))
                return False
            db.database.reset_all_data()
            await msg.reply(
                embed=discord.Embed(
                    title="Database reset complete",
                    description="Dropped and recreated the full database schema, then rebuilt tracked assets.",
                    color=SUCCESS_COLOR,
                )
            )
            return True

        if len(split) != 3:
            await msg.reply(embed=discord.Embed(description=usage, color=INFO_COLOR))
            return False

        raw_id = split[2]
        try:
            if target == "guild" and raw_id == MESSAGE_COMMAND_SPECIFY_LOCAL_SERVER:
                if msg.guild is None:
                    await msg.reply(get("commands.admin.guild_required_for_this"))
                    return False
                entity_id = msg.guild.id
            else:
                entity_id = int(raw_id)
        except ValueError:
            await msg.reply(embed=discord.Embed(description=usage, color=INFO_COLOR))
            return False

        if target == "game":
            recreated = db.database.reset_game_data(entity_id)
            await msg.reply(
                embed=discord.Embed(
                    title="Game reset complete",
                    description=(
                        f"Deleted all rows related to game `{entity_id}` and recreated "
                        f"`{recreated.game_name}` as game id `{recreated.game_id}`."
                    ),
                    color=SUCCESS_COLOR,
                )
            )
            return True

        if target == "user":
            db.database.reset_user_data(entity_id)
            await msg.reply(
                embed=discord.Embed(
                    title="User reset complete",
                    description=f"Deleted all rows related to user `{entity_id}` and recreated a blank user record.",
                    color=SUCCESS_COLOR,
                )
            )
            return True

        if target == "guild":
            db.database.reset_guild_data(entity_id)
            await msg.reply(
                embed=discord.Embed(
                    title="Guild reset complete",
                    description=f"Deleted all rows related to guild `{entity_id}` and recreated a blank guild record.",
                    color=SUCCESS_COLOR,
                )
            )
            return True

        await msg.reply(embed=discord.Embed(description=usage, color=INFO_COLOR))
        return False


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
