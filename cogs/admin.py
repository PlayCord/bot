import logging
import traceback

from discord.ext import commands

from configuration.constants import *
from utils.embeds import ErrorEmbed

log = logging.getLogger(LOGGING_ROOT)


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
