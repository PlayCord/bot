import logging

from discord.ext import commands

from configuration.constants import *
from utils.conversion import contextify

log = logging.getLogger(LOGGING_ROOT)


class MatchmakingCog(commands.Cog):
    def __init__(self, bot: discord.Client):
        self.bot = bot

    # No specific commands here yet as they are mostly subcommands of playcord or play
    # But we can store callbacks here

    @commands.Cog.listener()
    async def on_interaction(self, ctx: discord.Interaction) -> None:
        """
        Callback activated after every bot interaction.
        """
        custom_id = ctx.data.get("custom_id")
        if custom_id is None:
            return

        if (
                custom_id.startswith(BUTTON_PREFIX_JOIN)
                or custom_id.startswith(BUTTON_PREFIX_LEAVE)
                or custom_id.startswith(BUTTON_PREFIX_START)
        ):
            await self.matchmaking_button_callback(ctx)
        elif custom_id.startswith(BUTTON_PREFIX_INVITE):
            await self.invite_accept_callback(ctx)

    async def matchmaking_button_callback(self, ctx: discord.Interaction) -> None:
        """
        Handle matchmaking button (Join/Leave/Start)
        """
        await ctx.response.defer()
        f_log = log.getChild("callback.matchmaking_button")

        # Get interaction context
        interaction_context = contextify(ctx)
        f_log.info(
            f"matchmaking button pressed! ID: {ctx.data['custom_id']} context: {interaction_context}"
        )

        # Leading ID of custom ID string
        if ctx.data["custom_id"].startswith(BUTTON_PREFIX_JOIN):
            leading_str = BUTTON_PREFIX_JOIN
        elif ctx.data["custom_id"].startswith(BUTTON_PREFIX_LEAVE):
            leading_str = BUTTON_PREFIX_LEAVE
        else:
            leading_str = BUTTON_PREFIX_START

        # Get the MatchmakingInterface id (message ID)
        matchmaking_id = int(ctx.data["custom_id"].replace(leading_str, ""))

        # Check if it exists
        if matchmaking_id not in CURRENT_MATCHMAKING:
            f_log.debug(
                f"Matchmaking expired when trying to press button: {interaction_context}"
            )
            await ctx.followup.send(
                "This matchmaking session is over. Sorry about that :(", ephemeral=True
            )
            return

        matchmaker = CURRENT_MATCHMAKING[matchmaking_id]

        # Call MatchmakingInterface callbacks
        if leading_str == BUTTON_PREFIX_JOIN:
            await matchmaker.callback_ready_game(ctx)
        elif leading_str == BUTTON_PREFIX_LEAVE:
            await matchmaker.callback_leave_game(ctx)
        else:
            await matchmaker.callback_start_game(ctx)

    async def invite_accept_callback(self, ctx: discord.Interaction) -> None:
        """
        Invite accept button callback.
        """
        await ctx.response.defer()
        f_log = log.getChild("callback.invite_accept")

        matchmaking_id = int(ctx.data["custom_id"].replace(BUTTON_PREFIX_INVITE, ""))

        if matchmaking_id not in CURRENT_MATCHMAKING:
            await ctx.followup.send(
                "This game has already started or been cancelled.", ephemeral=True
            )
            return

        matchmaker = CURRENT_MATCHMAKING[matchmaking_id]
        success = await matchmaker.accept_invite(ctx)

        if success:
            await ctx.followup.send("Successfully joined the game!", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MatchmakingCog(bot))
