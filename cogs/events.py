import asyncio
import logging

from discord.ext import commands

from configuration.constants import *
from utils import database as db
from utils.embeds import CustomEmbed

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

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        f_log = log.getChild("event.guild_join")
        f_log.info(f"Added to guild {guild.name!r} ! (id={guild.id})")

        embed = CustomEmbed(title=WELCOME_MESSAGE[0][0], description=WELCOME_MESSAGE[0][1], color=EMBED_COLOR)
        for line in WELCOME_MESSAGE[1:]:
            embed.add_field(name=line[0], value=line[1])

        try:
            await guild.system_channel.send(embed=embed)
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
        
        # If user is a participant, allow the message
        if message.author.id in participant_ids:
            return
        
        f_log = log.getChild("event.thread_policy")
        f_log.debug(f"Non-participant {message.author.id} sent message in game thread {message.channel.id}")
        
        # Delete message if configured to do so
        if THREAD_POLICY_DELETE_NON_PARTICIPANT_MESSAGES:
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
            if current_time - last_warned > 60:
                self._warned_users[thread_id][user_id] = current_time
                try:
                    warning = await message.channel.send(
                        f"{message.author.mention} {THREAD_POLICY_WARNING_MESSAGE}",
                    )
                    await warning.delete(delay=10)
                except discord.Forbidden:
                    f_log.warning(f"Cannot send warning - missing permissions in thread {message.channel.id}")

    async def presence(self) -> None:
        presence_logger = logging.getLogger("playcord.presence")
        if not self.presence_lock.locked():
            async with self.presence_lock:
                while True:
                    options = []
                    for game in GAME_TYPES:
                        options.append(f"Playing {GAME_TYPES[game][1]}...")
                    options.extend(PRESENCE_PRESETS)

                    for option in options:
                        activity = discord.Activity(type=discord.ActivityType.playing, name=option)
                        await self.bot.change_presence(activity=activity)
                        await asyncio.sleep(PRESENCE_TIMEOUT)


async def setup(bot: commands.Bot):
    await bot.add_cog(EventsCog(bot))
