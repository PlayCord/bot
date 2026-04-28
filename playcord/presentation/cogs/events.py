import asyncio
import shutil
import subprocess

import discord
from discord.ext import commands

from playcord.infrastructure.app_constants import (
    ANALYTICS_PERIODIC_FLUSH_INITIAL_DELAY_SECONDS,
    ANALYTICS_PERIODIC_FLUSH_INTERVAL_SECONDS,
    EPHEMERAL_DELETE_AFTER,
    ERROR_NO_SYSTEM_CHANNEL,
    GAME_TYPES,
    PRESENCE_TIMEOUT,
    THREAD_POLICY_DELETE_NON_PARTICIPANT_MESSAGES,
    THREAD_POLICY_PARTICIPANTS_COMMANDS_ONLY,
    THREAD_POLICY_SPECTATORS_SILENT,
    THREAD_POLICY_WARN_NON_PARTICIPANTS,
    THREAD_POLICY_WARNING_MESSAGE,
    VERSION,
)
from playcord.infrastructure.locale import fmt, get
from playcord.infrastructure.logging import get_logger
from playcord.infrastructure.runtime_config import get_settings
from playcord.utils import analytics as analytics_mod
from playcord.utils.containers import CustomContainer, container_send_kwargs

log = get_logger()


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.presence_lock = asyncio.Lock()
        self._warned_users = (
            {}
        )  # {thread_id: {user_id: timestamp}} - track warnings to avoid spam
        # Build the version presence string.
        # If git is available and we can read the short commit hash, show:
        #   vx.y.z • f9ab9b
        # Otherwise just:
        #   vx.y.z
        version_base = f"v{VERSION}"
        git_executable = shutil.which("git")
        git_log = log.getChild("git")
        if not git_executable:
            # Git isn't installed or isn't in the system's PATH at all
            git_log.debug(
                "git executable not found in PATH; using version base %s", version_base
            )
            self.version = version_base
        else:
            try:
                proc = subprocess.run(
                    [git_executable, "rev-parse", "--short", "HEAD"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                short = proc.stdout.strip()

                if short:
                    self.version = f"{version_base} \u2022 {short}"
                    git_log.info(
                        "Using git short commit %s for presence version", short
                    )
                else:
                    git_log.debug(
                        "Git returned empty short hash; using version base %s",
                        version_base,
                    )
                    self.version = version_base

            except subprocess.CalledProcessError as e:
                # This catches errors if the command runs but fails
                # (e.g., the ".." directory is not actually a git repository)
                git_log.debug(
                    "git rev-parse failed: %s; using version base %s", e, version_base
                )
                self.version = version_base
            except FileNotFoundError as e:
                # Failsafe in case shutil.which lied to us
                git_log.warning(
                    "git executable disappeared or is not runnable: %s; "
                    "using version base %s",
                    e,
                    version_base,
                )
                self.version = version_base

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        startup_logger = log.getChild("startup")
        startup_logger.info("Client connected and ready.")
        self.bot.loop.create_task(self.presence())
        self.bot.loop.create_task(self._analytics_periodic_flush())

    async def _analytics_periodic_flush(self) -> None:
        """Retry any buffered analytics rows after failed DB writes."""
        await asyncio.sleep(ANALYTICS_PERIODIC_FLUSH_INITIAL_DELAY_SECONDS)
        while True:
            try:
                log.getChild("analytics.flush").debug(
                    "Attempting analytics flush and cleanup"
                )
                analytics_mod.flush_events()
                self.bot.container.guilds.cleanup_old_analytics(
                    days=get_settings().analytics_retention_days
                )
                log.getChild("analytics.flush").debug(
                    "Cleanup_old_analytics completed (retention_days=%s)",
                    get_settings().analytics_retention_days,
                )
            except Exception:
                log.exception("Periodic analytics flush/cleanup failed")
            await asyncio.sleep(ANALYTICS_PERIODIC_FLUSH_INTERVAL_SECONDS)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        f_log = log.getChild("event.guild_join")
        f_log.info(f"Added to guild {guild.name!r} ! (id={guild.id})")

        container = CustomContainer(
            title=fmt("welcome.title", name=get("brand.name")),
            description=get("welcome.description"),
        )
        container.add_field(
            name=get("welcome.fields.games.name"),
            value=get("welcome.fields.games.value"),
        )
        container.add_field(
            name=get("welcome.fields.rating.name"),
            value=get("welcome.fields.rating.value"),
        )
        container.add_field(
            name=get("welcome.fields.help.name"),
            value=fmt("welcome.fields.help.value", github_url=get("brand.github_url")),
        )
        container.add_field(
            name=get("welcome.fields.playcord_channel.name"),
            value=get("welcome.fields.playcord_channel.value"),
            inline=False,
        )

        try:
            f_log.debug(
                "Sending welcome message to guild.system_channel for guild id=%s",
                guild.id,
            )
            await guild.system_channel.send(**container_send_kwargs(container))
        except AttributeError:
            f_log.info(ERROR_NO_SYSTEM_CHANNEL)
        except discord.Forbidden:
            f_log.warning(
                "Missing permissions to send welcome message to guild %s (id=%s)",
                guild.name,
                guild.id,
            )
        except Exception:
            f_log.exception(
                "Failed to send welcome message to guild %s (id=%s)",
                guild.name,
                guild.id,
            )

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        f_log = log.getChild("event.guild_remove")
        f_log.info(f"Removed from guild {guild.name!r}! (id={guild.id}).")
        try:
            self.bot.container.guilds.delete_guild(guild.id)
            f_log.info(f"Successfully purged data for guild {guild.id}")
        except Exception as e:
            f_log.exception("Failed to purge data for guild %s: %s", guild.id, e)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """
        Handle messages in game threads - enforce thread policy for non-participants.
        """
        # Ignore messages from bots (including ourselves)
        if message.author.bot:
            log.getChild("event.thread_policy").debug(
                "Ignoring message from bot user %s in channel %s",
                getattr(message.author, "id", None),
                getattr(message.channel, "id", None),
            )
            return

        # Only apply to private threads (game threads)
        if message.channel.type != discord.ChannelType.private_thread:
            log.getChild("event.thread_policy").debug(
                "Ignoring non-private-thread message in channel %s",
                getattr(message.channel, "id", None),
            )
            return

        # Check if this thread has an active game
        reg = self.bot.container.registry
        if message.channel.id not in reg.games_by_thread_id:
            log.getChild("event.thread_policy").debug(
                "No active game for thread %s", message.channel.id
            )
            return

        game = reg.games_by_thread_id[message.channel.id]
        participant_ids = {p.id for p in game.players}

        # If user is a participant, optionally restrict to slash-style messages only
        if message.author.id in participant_ids:
            f_log = log.getChild("event.thread_policy.participant")
            f_log.debug(
                "Participant %s sent message in thread %s",
                message.author.id,
                message.channel.id,
            )
            if THREAD_POLICY_PARTICIPANTS_COMMANDS_ONLY:
                text = (message.content or "").strip()
                if text and not text.startswith("/"):
                    try:
                        await message.delete()
                        f_log.info(
                            "Deleted non-command message from participant %s "
                            "in thread %s",
                            message.author.id,
                            message.channel.id,
                        )
                    except discord.Forbidden:
                        f_log.warning(
                            "Cannot delete participant message - missing "
                            "permissions in thread %s",
                            message.channel.id,
                        )
                    except discord.NotFound:
                        f_log.debug(
                            "Message to delete was not found (already deleted)"
                        )
            return

        f_log = log.getChild("event.thread_policy")
        f_log.debug(
            "Non-participant %s sent message in game thread %s",
            message.author.id,
            message.channel.id,
        )

        # Delete message if configured to do so (spectator-silent is independent of the generic delete flag)
        if (
            THREAD_POLICY_SPECTATORS_SILENT
            or THREAD_POLICY_DELETE_NON_PARTICIPANT_MESSAGES
        ):
            try:
                await message.delete()
                f_log.info(
                    "Deleted message from non-participant %s in thread %s",
                    message.author.id,
                    message.channel.id,
                )
            except discord.Forbidden:
                f_log.warning(
                    "Cannot delete message - missing permissions in thread %s",
                    message.channel.id,
                )
            except discord.NotFound:
                f_log.debug(
                    "Message already deleted when attempting to remove non-participant message in thread %s",
                    message.channel.id,
                )

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
                    f_log.info(
                        "Sending warning to non-participant %s in thread %s",
                        user_id,
                        thread_id,
                    )
                    warning = await message.channel.send(
                        f"{message.author.mention} {THREAD_POLICY_WARNING_MESSAGE}",
                    )
                    await warning.delete(delay=EPHEMERAL_DELETE_AFTER)
                except discord.Forbidden:
                    f_log.warning(
                        "Cannot send warning - missing permissions in thread %s",
                        message.channel.id,
                    )
                except Exception:
                    f_log.exception(
                        "Failed to send/delete warning message in thread %s for user %s",
                        thread_id,
                        user_id,
                    )
            else:
                f_log.debug(
                    "Skipping warning for user %s in thread %s due to rate limiting (last_warned=%s)",
                    user_id,
                    thread_id,
                    last_warned,
                )

    async def presence(self) -> None:
        if not self.presence_lock.locked():
            async with self.presence_lock:
                while True:
                    reg = self.bot.container.registry
                    options = [
                        fmt("presence.catalog_games", count=len(GAME_TYPES)),
                        fmt("presence.users_playing", count=len(reg.user_to_game)),
                        fmt(
                            "presence.users_matchmaking",
                            count=len(reg.user_to_matchmaking),
                        ),
                        fmt(
                            "presence.games_happening_now",
                            count=len(reg.games_by_thread_id),
                        ),
                    ]
                    # Include the version (and commit if available) as one of the rotating presence entries.
                    options.append(self.version)
                    for option in options:
                        try:
                            activity = discord.Activity(
                                type=discord.ActivityType.playing, name=option
                            )
                            log.getChild("presence").debug(
                                "Setting presence to: %s", option
                            )
                            await self.bot.change_presence(activity=activity)
                        except Exception:
                            log.getChild("presence").exception(
                                "Failed to change presence to %s", option
                            )
                        await asyncio.sleep(PRESENCE_TIMEOUT)


async def setup(bot: commands.Bot):
    await bot.add_cog(EventsCog(bot))
