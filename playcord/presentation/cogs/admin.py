import asyncio
import traceback

import discord
from discord.ext import commands

from playcord.infrastructure.analytics_client import (
    render_analytics_markdown_summary,
)
from playcord.infrastructure.constants import (
    INFO_COLOR,
    LOGGING_ROOT,
    MESSAGE_COMMAND_ANALYTICS,
    MESSAGE_COMMAND_CLEAR,
    MESSAGE_COMMAND_DBRESET,
    MESSAGE_COMMAND_FAILED,
    MESSAGE_COMMAND_PENDING,
    MESSAGE_COMMAND_SPECIFY_LOCAL_SERVER,
    MESSAGE_COMMAND_SUCCEEDED,
    MESSAGE_COMMAND_SYNC,
    MESSAGE_COMMAND_TREEDIFF,
    SUCCESS_COLOR,
    WARNING_COLOR,
)
from playcord.infrastructure.locale import fmt, get
from playcord.infrastructure.logging import get_logger
from playcord.presentation.bot import PlayCordBot
from playcord.presentation.ui.analytics_charts import (
    render_analytics_matplotlib_summary,
)
from playcord.presentation.ui.containers import (
    CustomContainer,
    append_container_sections,
    container_send_kwargs,
    lines_to_container_sections,
)

log = get_logger()


async def _add_processing_reaction(msg: discord.Message) -> None:
    try:
        await msg.add_reaction(MESSAGE_COMMAND_PENDING)
    except discord.HTTPException:
        pass


async def _finalize_admin_reactions(
    msg: discord.Message, bot_user: discord.abc.User, *, success: bool,
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


def _admin_error_text(what_failed: str, reason: str | None = None) -> str:
    head = (what_failed or "").strip()
    tail = (reason or "").strip()
    text = f"{head}\n\n{tail}".strip() if tail else head
    if len(text) > 1900:
        return text[:1897] + "..."
    return text


class AdminCog(commands.Cog):
    def __init__(self, bot: PlayCordBot):
        self.bot = bot
        self._analytics = bot.container.analytics_repository
        self._guilds = bot.container.guilds_repository

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
                    content=_admin_error_text(
                        get("commands.admin.task_unexpected_error"),
                        traceback.format_exc(),
                    ),
                )
            except discord.HTTPException:
                pass
            ok = False
        finally:
            await _finalize_admin_reactions(msg, self.bot.user, success=ok)

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message) -> None:
        """Handle message commands for bot administration
        """
        if msg.author.bot or msg.author.id not in self.bot.effective_owner_ids:
            return

        f_log = log.getChild("event.on_message")

        if msg.content.startswith(f"{LOGGING_ROOT}/"):
            f_log.info(f"Received authorized message command {msg.content!r}.")

        # Sync (Discord API — can be slow)
        if msg.content.startswith(f"{LOGGING_ROOT}/{MESSAGE_COMMAND_SYNC}"):
            asyncio.create_task(self._run_long_admin_task(msg, self._task_sync))

        # Analytics — owner message `playcord/analytics [hours]` (DB + matplotlib)
        elif msg.content.startswith(f"{LOGGING_ROOT}/{MESSAGE_COMMAND_ANALYTICS}"):
            asyncio.create_task(self._run_long_admin_task(msg, self._task_analytics))

        # Slash tree deep diff
        elif msg.content.startswith(f"{LOGGING_ROOT}/{MESSAGE_COMMAND_TREEDIFF}"):
            asyncio.create_task(self._run_long_admin_task(msg, self._task_treediff))

        # Clear (tree sync — can be slow)
        elif msg.content.startswith(f"{LOGGING_ROOT}/{MESSAGE_COMMAND_CLEAR}"):
            asyncio.create_task(self._run_long_admin_task(msg, self._task_clear))

        # Database reset helpers
        elif msg.content.startswith(f"{LOGGING_ROOT}/{MESSAGE_COMMAND_DBRESET}"):
            asyncio.create_task(self._run_long_admin_task(msg, self._task_dbreset))

    async def _task_sync(self, msg: discord.Message) -> bool:
        f_log = log.getChild("event.on_message")
        split = msg.content.split()
        if len(split) == 1:
            try:
                await self.bot.tree.sync()
            except Exception as e:
                await msg.reply(
                    content=_admin_error_text(
                        fmt(
                            "commands.admin.sync_failed",
                            error_type=type(e).__name__,
                        ),
                        traceback.format_exc(),
                    ),
                )
                return False
            f_log.info(
                f"Performed authorized sync from user {msg.author.id} to all guilds.",
            )
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
                await msg.reply(
                    fmt("commands.admin.sync_usage", prefix=f"{LOGGING_ROOT}/"),
                )
                return False

        self.bot.tree.copy_global_to(guild=g)
        try:
            await self.bot.tree.sync(guild=g)
        except Exception as e:
            await msg.reply(
                content=_admin_error_text(
                    fmt(
                        "commands.admin.sync_failed",
                        error_type=type(e).__name__,
                    ),
                    traceback.format_exc(),
                ),
            )
            return False
        f_log.info(
            f"Performed authorized sync from user {msg.author.id} to guild {g.id}",
        )
        return True

    async def _task_analytics(self, msg: discord.Message) -> bool:
        split = msg.content.split()
        hours = 24
        if len(split) >= 2:
            try:
                hours = int(split[1])
            except ValueError:
                await msg.reply(
                    **container_send_kwargs(
                        CustomContainer(
                            description=fmt(
                                "commands.analytics.message_usage",
                                prefix=f"{LOGGING_ROOT}/",
                            ),
                            color=INFO_COLOR,
                        ),
                    ),
                )
                return False
        hours = max(1, min(hours, 24 * 30))
        counts = self._analytics.get_summary(hours=hours)
        by_game = self._analytics.get_event_counts_by_game(hours=hours)
        recent = self._analytics.get_recent_events(hours=hours, limit=60)
        if not counts and not recent and not by_game:
            await msg.reply(
                **container_send_kwargs(
                    CustomContainer(
                        title=fmt("commands.analytics.embed_title", hours=hours),
                        description=fmt(
                            "commands.analytics.message_empty", hours=hours,
                        ),
                    ),
                ),
            )
            return True

        chart_buf = await asyncio.to_thread(
            render_analytics_matplotlib_summary, counts, by_game, hours,
        )
        main_container = CustomContainer(
            title=fmt("commands.analytics.embed_title", hours=hours),
            description=(
                get("commands.analytics.embed_description")
                if chart_buf is not None
                else get("commands.analytics.embed_no_chart")
            ),
        )
        if chart_buf is not None:
            chart_buf.seek(0)
            main_container.set_image(url="attachment://playcord-analytics.png")

        recent_lines: list[str] = render_analytics_markdown_summary(
            counts, by_game, recent, hours,
        )
        append_container_sections(
            main_container,
            lines_to_container_sections(recent_lines),
            first_name=get("commands.analytics.field_recent"),
            truncated_note=get("commands.analytics.recent_truncated_note"),
        )

        if chart_buf is not None:
            await msg.reply(
                **container_send_kwargs(
                    main_container,
                    files=[discord.File(chart_buf, filename="playcord-analytics.png")],
                ),
            )
        else:
            await msg.reply(**container_send_kwargs(main_container))
        return True

    async def _task_treediff(self, msg: discord.Message) -> bool:
        split = msg.content.split()
        guild: discord.Guild | discord.Object | None = None
        if len(split) >= 2:
            if split[1] == MESSAGE_COMMAND_SPECIFY_LOCAL_SERVER:
                if msg.guild is None:
                    await msg.reply(
                        **container_send_kwargs(
                            CustomContainer(
                                description=get("commands.treediff.need_guild"),
                                color=WARNING_COLOR,
                            ),
                        ),
                    )
                    return False
                guild = msg.guild
            else:
                try:
                    guild = discord.Object(id=int(split[1]))
                except ValueError:
                    await msg.reply(
                        **container_send_kwargs(
                            CustomContainer(
                                description=fmt(
                                    "commands.treediff.message_usage",
                                    prefix=f"{LOGGING_ROOT}/",
                                ),
                                color=INFO_COLOR,
                            ),
                        ),
                    )
                    return False
        try:
            from playcord.presentation.interactions.command_tree_sync import (
                drift_to_container,
                fetch_and_analyze_tree,
            )

            drift = await fetch_and_analyze_tree(self.bot.tree, guild=guild)
        except discord.HTTPException as e:
            await msg.reply(
                content=_admin_error_text(
                    get("commands.treediff.message_failed"),
                    str(e),
                ),
            )
            return False
        except Exception:
            await msg.reply(
                content=_admin_error_text(
                    get("commands.treediff.message_failed"),
                    traceback.format_exc(),
                ),
            )
            return False
        diff_container = drift_to_container(
            drift,
            color=None,
            title=get("commands.treediff.embed_title"),
        )
        await msg.reply(**container_send_kwargs(diff_container))
        return True

    async def _task_clear(self, msg: discord.Message) -> bool:
        f_log = log.getChild("event.on_message")
        split = msg.content.split()
        if len(split) == 1:
            self.bot.tree.clear_commands(guild=None)
            await self.bot.tree.sync()
            f_log.info(
                f"Performed authorized command tree clear from user "
                f"{msg.author.id} to all guilds.",
            )
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
                await msg.reply(
                    fmt("commands.admin.clear_usage", prefix=f"{LOGGING_ROOT}/"),
                )
                return False
        self.bot.tree.clear_commands(guild=g)
        await self.bot.tree.sync(guild=g)
        f_log.info(
            f"Performed authorized command tree clear from user "
            f"{msg.author.id} to guild {g.id}",
        )
        return True

    async def _task_dbreset(self, msg: discord.Message) -> bool:
        f_log = log.getChild("event.on_message")
        f_log.debug(
            "_task_dbreset called by user=%r content=%r",
            msg.author.id if msg.author else None,
            msg.content,
        )
        split = msg.content.split()
        usage = (
            f"`{LOGGING_ROOT}/{MESSAGE_COMMAND_DBRESET} game <id>`\n"
            f"`{LOGGING_ROOT}/{MESSAGE_COMMAND_DBRESET} all`\n"
            f"`{LOGGING_ROOT}/{MESSAGE_COMMAND_DBRESET} user <id>`\n"
            f"`{LOGGING_ROOT}/{MESSAGE_COMMAND_DBRESET} guild "
            f"<id|{MESSAGE_COMMAND_SPECIFY_LOCAL_SERVER}>`"
        )
        if len(split) < 2:
            await msg.reply(
                **container_send_kwargs(
                    CustomContainer(description=usage, color=INFO_COLOR),
                ),
            )
            return False

        target = split[1].lower()
        if target == "all":
            if len(split) != 2:
                await msg.reply(
                    **container_send_kwargs(
                        CustomContainer(description=usage, color=INFO_COLOR),
                    ),
                )
                return False
            self._guilds.reset_all_data()
            f_log.info(
                "Performed full database reset requested by user %r",
                msg.author.id if msg.author else None,
            )
            await msg.reply(
                **container_send_kwargs(
                    CustomContainer(
                        title=get("commands.admin.dbreset_all_title"),
                        description=get("commands.admin.dbreset_all_description"),
                        color=SUCCESS_COLOR,
                    ),
                ),
            )
            return True

        if len(split) != 3:
            await msg.reply(
                **container_send_kwargs(
                    CustomContainer(description=usage, color=INFO_COLOR),
                ),
            )
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
            await msg.reply(
                **container_send_kwargs(
                    CustomContainer(description=usage, color=INFO_COLOR),
                ),
            )
            return False

        if target == "game":
            recreated = self._guilds.reset_game_data(entity_id)
            f_log.info(
                "Performed game reset for game_id=%r requested by user %r",
                entity_id,
                msg.author.id if msg.author else None,
            )
            await msg.reply(
                **container_send_kwargs(
                    CustomContainer(
                        title=get("commands.admin.dbreset_game_title"),
                        description=fmt(
                            "commands.admin.dbreset_game_description",
                            entity_id=entity_id,
                            game_name=recreated.game_name,
                            game_id=recreated.game_id,
                        ),
                        color=SUCCESS_COLOR,
                    ),
                ),
            )
            return True

        if target == "user":
            self._guilds.reset_user_data(entity_id)
            f_log.info(
                "Performed user reset for user_id=%r requested by user %r",
                entity_id,
                msg.author.id if msg.author else None,
            )
            await msg.reply(
                **container_send_kwargs(
                    CustomContainer(
                        title=get("commands.admin.dbreset_user_title"),
                        description=fmt(
                            "commands.admin.dbreset_user_description",
                            entity_id=entity_id,
                        ),
                        color=SUCCESS_COLOR,
                    ),
                ),
            )
            return True

        if target == "guild":
            self._guilds.reset_guild_data(entity_id)
            f_log.info(
                "Performed guild reset for guild_id=%r requested by user %r",
                entity_id,
                msg.author.id if msg.author else None,
            )
            await msg.reply(
                **container_send_kwargs(
                    CustomContainer(
                        title=get("commands.admin.dbreset_guild_title"),
                        description=fmt(
                            "commands.admin.dbreset_guild_description",
                            entity_id=entity_id,
                        ),
                        color=SUCCESS_COLOR,
                    ),
                ),
            )
            return True

        await msg.reply(
            **container_send_kwargs(
                CustomContainer(description=usage, color=INFO_COLOR),
            ),
        )
        return False


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
