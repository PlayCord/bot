import logging
import traceback

import discord
from discord.ext import commands

from configuration.constants import *
from utils import database as db
from utils.analytics import format_ascii_bar_chart, format_recent_event_row
from utils.embeds import ErrorEmbed
from utils.locale import fmt, get

log = logging.getLogger(LOGGING_ROOT)


def _chunk_discord_text(text: str, size: int = 1900):
    for i in range(0, len(text), size):
        yield text[i : i + size]


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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

        # Sync
        if msg.content.startswith(f"{LOGGING_ROOT}/{MESSAGE_COMMAND_SYNC}"):
            split = msg.content.split()
            if len(split) == 1:
                try:
                    await self.bot.tree.sync()
                except Exception as e:
                    await msg.add_reaction(MESSAGE_COMMAND_FAILED)
                    await msg.reply(embed=ErrorEmbed(what_failed=f"Couldn't sync commands! ({type(e)})",
                                                     reason=traceback.format_exc()))
                    return
                f_log.info(f"Performed authorized sync from user {msg.author.id} to all guilds.")
            else:
                if split[1] == MESSAGE_COMMAND_SPECIFY_LOCAL_SERVER:
                    g = msg.guild
                else:
                    try:
                        g = discord.Object(id=int(split[1]))
                    except ValueError:
                        return

                self.bot.tree.copy_global_to(guild=g)
                try:
                    await self.bot.tree.sync(guild=g)
                except Exception as e:
                    await msg.add_reaction(MESSAGE_COMMAND_FAILED)
                    await msg.reply(embed=ErrorEmbed(what_failed=f"Couldn't sync commands! ({type(e)})",
                                                     reason=traceback.format_exc()))
                    return
                f_log.info(f"Performed authorized sync from user {msg.author.id} to guild {msg.guild.id}")
            await msg.add_reaction(MESSAGE_COMMAND_SUCCEEDED)

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

        # Analytics (counts + recent rows; not exposed as a slash command)
        elif msg.content.startswith(f"{LOGGING_ROOT}/{MESSAGE_COMMAND_ANALYTICS}"):
            split = msg.content.split()
            hours = 24
            if len(split) >= 2:
                try:
                    hours = int(split[1])
                except ValueError:
                    await msg.reply(fmt("commands.analytics.message_usage", prefix=f"{LOGGING_ROOT}/"))
                    await msg.add_reaction(MESSAGE_COMMAND_FAILED)
                    return
            hours = max(1, min(hours, 24 * 30))
            counts = db.database.get_analytics_event_counts(hours=hours)
            by_game = db.database.get_analytics_event_counts_by_game(hours=hours)
            recent = db.database.get_analytics_recent_events(hours=hours, limit=60)
            if not counts and not recent and not by_game:
                await msg.reply(fmt("commands.analytics.message_empty", hours=hours))
                await msg.add_reaction(MESSAGE_COMMAND_SUCCEEDED)
                return
            lines: list[str] = [f"**Analytics** — last **{hours}** hour(s)", ""]
            lines.append(get("commands.analytics.message_counts_header"))
            if counts:
                lines.extend(format_ascii_bar_chart(counts, label_key="event_type", value_key="cnt"))
            else:
                lines.append("_(none)_")
            lines.extend(("", get("commands.analytics.message_by_game_header")))
            if by_game:
                lines.extend(format_ascii_bar_chart(by_game, label_key="game_type", value_key="cnt"))
            else:
                lines.append("_(none)_")
            lines.extend(("", get("commands.analytics.message_recent_header")))
            if recent:
                lines.extend(format_recent_event_row(r) for r in recent)
            else:
                lines.append("_(none)_")
            body = "\n".join(lines)
            first = True
            for chunk in _chunk_discord_text(body):
                if first:
                    await msg.reply(chunk)
                    first = False
                else:
                    await msg.channel.send(chunk)
            await msg.add_reaction(MESSAGE_COMMAND_SUCCEEDED)

        # Slash tree deep diff (local CommandTree vs Discord API)
        elif msg.content.startswith(f"{LOGGING_ROOT}/{MESSAGE_COMMAND_TREEDIFF}"):
            split = msg.content.split()
            guild: discord.Guild | discord.Object | None = None
            if len(split) >= 2:
                if split[1] == MESSAGE_COMMAND_SPECIFY_LOCAL_SERVER:
                    if msg.guild is None:
                        await msg.reply(get("commands.treediff.need_guild"))
                        await msg.add_reaction(MESSAGE_COMMAND_FAILED)
                        return
                    guild = msg.guild
                else:
                    try:
                        guild = discord.Object(id=int(split[1]))
                    except ValueError:
                        await msg.reply(fmt("commands.treediff.message_usage", prefix=f"{LOGGING_ROOT}/"))
                        await msg.add_reaction(MESSAGE_COMMAND_FAILED)
                        return
            try:
                from utils.command_tree_diff import fetch_and_analyze_tree, format_drift_report

                drift = await fetch_and_analyze_tree(self.bot.tree, guild=guild)
            except discord.HTTPException as e:
                await msg.add_reaction(MESSAGE_COMMAND_FAILED)
                await msg.reply(
                    embed=ErrorEmbed(
                        what_failed=get("commands.treediff.message_failed"),
                        reason=str(e),
                    )
                )
                return
            except Exception as e:
                await msg.add_reaction(MESSAGE_COMMAND_FAILED)
                await msg.reply(
                    embed=ErrorEmbed(
                        what_failed=get("commands.treediff.message_failed"),
                        reason=traceback.format_exc(),
                    )
                )
                return
            report = "### Command tree (local vs API)\n" + format_drift_report(drift, max_lines=45)
            first = True
            for chunk in _chunk_discord_text(report):
                if first:
                    await msg.reply(chunk)
                    first = False
                else:
                    await msg.channel.send(chunk)
            await msg.add_reaction(MESSAGE_COMMAND_SUCCEEDED)

        # Clear
        elif msg.content.startswith(f"{LOGGING_ROOT}/{MESSAGE_COMMAND_CLEAR}"):
            split = msg.content.split()
            if len(split) == 1:
                self.bot.tree.clear_commands(guild=None)
                await self.bot.tree.sync()
                f_log.info(f"Performed authorized command tree clear from user {msg.author.id} to all guilds.")
            else:
                if split[1] == MESSAGE_COMMAND_SPECIFY_LOCAL_SERVER:
                    g = msg.guild
                else:
                    g = discord.Object(id=int(split[1]))
                self.bot.tree.clear_commands(guild=g)
                await self.bot.tree.sync(guild=g)
                f_log.info(f"Performed authorized command tree clear from user {msg.author.id} to guild {msg.guild.id}")
            await msg.add_reaction(MESSAGE_COMMAND_SUCCEEDED)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
