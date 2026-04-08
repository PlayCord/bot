import asyncio
import logging

import discord
from discord.ext import commands

from configuration.constants import (
    ANALYTICS_PERIODIC_FLUSH_INITIAL_DELAY_SECONDS,
    ANALYTICS_PERIODIC_FLUSH_INTERVAL_SECONDS,
    ANALYTICS_RETENTION_DAYS,
    CURRENT_GAMES,
    EPHEMERAL_DELETE_AFTER,
    ERROR_NO_SYSTEM_CHANNEL,
    GAME_TYPES,
    IN_GAME,
    IN_MATCHMAKING,
    LOGGING_ROOT,
    PRESENCE_TIMEOUT,
    THREAD_POLICY_DELETE_NON_PARTICIPANT_MESSAGES,
    THREAD_POLICY_PARTICIPANTS_COMMANDS_ONLY,
    THREAD_POLICY_SPECTATORS_SILENT,
    THREAD_POLICY_WARN_NON_PARTICIPANTS,
    THREAD_POLICY_WARNING_MESSAGE,
    WELCOME_MESSAGE,
)
from utils import analytics as analytics_mod
from utils import database as db
from utils.containers import CustomContainer, container_send_kwargs
from utils.locale import get, fmt

log = logging.getLogger(LOGGING_ROOT)


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.presence_lock = asyncio.Lock()
        self._warned_users = {}  # {thread_id: {user_id: timestamp}} - track warnings to avoid spam

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        startup_logger = logging.getLogger(f"{LOGGING_ROOT}.startup")
        startup_logger.info(f"Client connected and ready.")
        self.bot.loop.create_task(self.presence())
        self.bot.loop.create_task(self._analytics_periodic_flush())

    async def _analytics_periodic_flush(self) -> None:
        """Retry any buffered analytics rows after failed DB writes."""
        await asyncio.sleep(ANALYTICS_PERIODIC_FLUSH_INITIAL_DELAY_SECONDS)
        while True:
            try:
                analytics_mod.flush_events()
                if db.database is not None:
                    db.database.cleanup_old_analytics(days=ANALYTICS_RETENTION_DAYS)
            except Exception:
                pass
            await asyncio.sleep(ANALYTICS_PERIODIC_FLUSH_INTERVAL_SECONDS)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        f_log = log.getChild("event.guild_join")
        f_log.info(f"Added to guild {guild.name!r} ! (id={guild.id})")

        container = CustomContainer(title=WELCOME_MESSAGE[0][0], description=WELCOME_MESSAGE[0][1])
        for line in WELCOME_MESSAGE[1:]:
            container.add_field(name=line[0], value=line[1])
        container.add_field(
            name=get("welcome.fields.playcord_channel.name"),
            value=get("welcome.fields.playcord_channel.value"),
            inline=False,
        )

        try:
            await guild.system_channel.send(**container_send_kwargs(container))
        except AttributeError:
            f_log.info(ERROR_NO_SYSTEM_CHANNEL)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        f_log = log.getChild("event.guild_remove")
        f_log.info(f"Removed from guild {guild.name!r}! (id={guild.id}).")
        try:
            db.database.delete_guild(guild.id)
            f_log.info(f"Successfully purged data for guild {guild.id}")
        except Exception as e:
            f_log.error(f"Failed to purge data for guild {guild.id}: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """
        Handle messages in game threads - enforce thread policy for non-participants.
        """
        # Ignore messages from bots (including ourselves)
        if message.author.bot:
            return

        # Only apply to private threads (game threads)
        if message.channel.type != discord.ChannelType.private_thread:
            return

        # Check if this thread has an active game
        if message.channel.id not in CURRENT_GAMES:
            return

        game = CURRENT_GAMES[message.channel.id]
        participant_ids = {p.id for p in game.players}

        # If user is a participant, optionally restrict to slash-style messages only
        if message.author.id in participant_ids:
            if THREAD_POLICY_PARTICIPANTS_COMMANDS_ONLY:
                text = (message.content or "").strip()
                if text and not text.startswith("/"):
                    try:
                        await message.delete()
                    except (discord.Forbidden, discord.NotFound):
                        pass
            return

        f_log = log.getChild("event.thread_policy")
        f_log.debug(f"Non-participant {message.author.id} sent message in game thread {message.channel.id}")

        # Delete message if configured to do so (spectator-silent is independent of the generic delete flag)
        if THREAD_POLICY_SPECTATORS_SILENT or THREAD_POLICY_DELETE_NON_PARTICIPANT_MESSAGES:
            try:
                await message.delete()
                f_log.info(f"Deleted message from non-participant {message.author.id} in thread {message.channel.id}")
            except discord.Forbidden:
                f_log.warning(f"Cannot delete message - missing permissions in thread {message.channel.id}")
            except discord.NotFound:
                pass  # Message already deleted

        # Warn the user (with rate limiting to avoid spam)
        if THREAD_POLICY_WARN_NON_PARTICIPANTS:
            import time
            current_time = time.time()
            thread_id = message.channel.id
            user_id = message.author.id

            # Initialize tracking for this thread if needed
            if thread_id not in self._warned_users:
                self._warned_users[thread_id] = {}

            # Only warn once per 60 seconds per user per thread
            last_warned = self._warned_users[thread_id].get(user_id, 0)
            if current_time - last_warned > PRESENCE_TIMEOUT:
                self._warned_users[thread_id][user_id] = current_time
                try:
                    warning = await message.channel.send(
                        f"{message.author.mention} {THREAD_POLICY_WARNING_MESSAGE}",
                    )
                    await warning.delete(delay=EPHEMERAL_DELETE_AFTER)
                except discord.Forbidden:
                    f_log.warning(f"Cannot send warning - missing permissions in thread {message.channel.id}")

    async def presence(self) -> None:
        if not self.presence_lock.locked():
            async with self.presence_lock:
                while True:
                    options = [
                        fmt("presence.catalog_games", count=len(GAME_TYPES)),
                        fmt("presence.users_playing", count=len(IN_GAME)),
                        fmt("presence.users_matchmaking", count=len(IN_MATCHMAKING)),
                        fmt("presence.games_happening_now", count=len(CURRENT_GAMES)),
                    ]
                    for option in options:
                        activity = discord.Activity(type=discord.ActivityType.playing, name=option)
                        await self.bot.change_presence(activity=activity)
                        await asyncio.sleep(PRESENCE_TIMEOUT)


async def setup(bot: commands.Bot):
    await bot.add_cog(EventsCog(bot))
