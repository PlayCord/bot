import logging

import discord
from discord.ext import commands

from configuration.constants import (
    BUTTON_PREFIX_INVITE,
    BUTTON_PREFIX_JOIN,
    BUTTON_PREFIX_LEAVE,
    BUTTON_PREFIX_LOBBY_OPT,
    BUTTON_PREFIX_LOBBY_ROLE,
    BUTTON_PREFIX_READY,
    CURRENT_MATCHMAKING,
    EPHEMERAL_DELETE_AFTER,
    LOGGING_ROOT,
)
from utils.conversion import contextify
from utils.discord_utils import followup_send
from utils.locale import get

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
        data = ctx.data if ctx.data is not None else {}
        custom_id = data.get("custom_id")
        if custom_id is None:
            return

        if custom_id.startswith(BUTTON_PREFIX_LOBBY_OPT):
            await self.lobby_select_callback(ctx)
        elif custom_id.startswith(BUTTON_PREFIX_LOBBY_ROLE):
            await self.lobby_role_select_callback(ctx)
        elif (
                custom_id.startswith(BUTTON_PREFIX_JOIN)
                or custom_id.startswith(BUTTON_PREFIX_LEAVE)
                or custom_id.startswith(BUTTON_PREFIX_READY)
        ):
            await self.matchmaking_button_callback(ctx)
        elif custom_id.startswith(BUTTON_PREFIX_INVITE):
            await self.invite_accept_callback(ctx)

    async def lobby_select_callback(self, ctx: discord.Interaction) -> None:
        """Lobby string-select for per-game match options (handled by MatchmakingInterface)."""
        await ctx.response.defer(ephemeral=True)
        f_log = log.getChild("callback.lobby_select")
        data = ctx.data if ctx.data is not None else {}
        cid = data.get("custom_id")
        if not cid or not cid.startswith(BUTTON_PREFIX_LOBBY_OPT):
            await followup_send(ctx,
                                content=get("matchmaking.invalid_interaction"),
                                ephemeral=True,
                                delete_after=EPHEMERAL_DELETE_AFTER,
                                )
            return
        rest = cid[len(BUTTON_PREFIX_LOBBY_OPT):]
        mid_str, _, key = rest.partition("/")
        if not mid_str or not key:
            await followup_send(ctx, content=get("matchmaking.invalid_button"), ephemeral=True,
                                delete_after=EPHEMERAL_DELETE_AFTER)
            return
        try:
            matchmaking_id = int(mid_str)
        except ValueError:
            await followup_send(ctx, content=get("matchmaking.invalid_button"), ephemeral=True,
                                delete_after=EPHEMERAL_DELETE_AFTER)
            return
        if matchmaking_id not in CURRENT_MATCHMAKING:
            await followup_send(ctx, content=get("matchmaking.session_expired"), ephemeral=True,
                                delete_after=EPHEMERAL_DELETE_AFTER)
            return
        f_log.debug("lobby option key=%r lobby=%s user=%s", key, matchmaking_id, ctx.user.id)
        matchmaker = CURRENT_MATCHMAKING[matchmaking_id]
        await matchmaker.callback_lobby_option(ctx, key)

    async def lobby_role_select_callback(self, ctx: discord.Interaction) -> None:
        """Per-player role select for CHOSEN :attr:`role_mode` (handled by MatchmakingInterface)."""
        await ctx.response.defer(ephemeral=True)
        f_log = log.getChild("callback.lobby_role_select")
        data = ctx.data if ctx.data is not None else {}
        cid = data.get("custom_id")
        if not cid or not cid.startswith(BUTTON_PREFIX_LOBBY_ROLE):
            await followup_send(ctx, content=get("matchmaking.invalid_interaction"), ephemeral=True,
                                delete_after=EPHEMERAL_DELETE_AFTER)
            return
        rest = cid[len(BUTTON_PREFIX_LOBBY_ROLE):]
        mid_str, _, pid_str = rest.partition("/")
        if not mid_str or not pid_str:
            await followup_send(ctx, content=get("matchmaking.invalid_button"), ephemeral=True,
                                delete_after=EPHEMERAL_DELETE_AFTER)
            return
        try:
            matchmaking_id = int(mid_str)
            player_id = int(pid_str)
        except ValueError:
            await followup_send(ctx, content=get("matchmaking.invalid_button"), ephemeral=True,
                                delete_after=EPHEMERAL_DELETE_AFTER)
            return
        if matchmaking_id not in CURRENT_MATCHMAKING:
            await followup_send(ctx, content=get("matchmaking.session_expired"), ephemeral=True,
                                delete_after=EPHEMERAL_DELETE_AFTER)
            return
        f_log.debug("lobby role pick lobby=%s player_id=%s user=%s", matchmaking_id, player_id, ctx.user.id)
        matchmaker = CURRENT_MATCHMAKING[matchmaking_id]
        await matchmaker.callback_role_select(ctx, player_id)

    async def matchmaking_button_callback(self, ctx: discord.Interaction) -> None:
        """
        Handle matchmaking button (Join / Leave / Ready)
        """
        await ctx.response.defer()
        f_log = log.getChild("callback.matchmaking_button")

        data = ctx.data if ctx.data is not None else {}
        cid = data.get("custom_id")
        if not cid:
            await followup_send(ctx, content=get("matchmaking.invalid_interaction"), ephemeral=True,
                                delete_after=EPHEMERAL_DELETE_AFTER)
            return

        # Get interaction context
        interaction_context = contextify(ctx)
        f_log.info(
            f"matchmaking button pressed! ID: {cid} context: {interaction_context}"
        )

        # Leading ID of custom ID string
        if cid.startswith(BUTTON_PREFIX_JOIN):
            leading_str = BUTTON_PREFIX_JOIN
        elif cid.startswith(BUTTON_PREFIX_LEAVE):
            leading_str = BUTTON_PREFIX_LEAVE
        elif cid.startswith(BUTTON_PREFIX_READY):
            leading_str = BUTTON_PREFIX_READY
        else:
            await followup_send(
                ctx,
                content=get("matchmaking.invalid_button"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        try:
            matchmaking_id = int(cid.replace(leading_str, ""))
        except ValueError:
            await followup_send(ctx, content=get("matchmaking.invalid_button"), ephemeral=True,
                                delete_after=EPHEMERAL_DELETE_AFTER)
            return

        # Check if it exists
        if matchmaking_id not in CURRENT_MATCHMAKING:
            f_log.debug(
                f"Matchmaking expired when trying to press button: {interaction_context}"
            )
            await followup_send(ctx,
                                content=get("matchmaking.session_expired"),
                                ephemeral=True,
                                delete_after=EPHEMERAL_DELETE_AFTER,
                                )
            return

        matchmaker = CURRENT_MATCHMAKING[matchmaking_id]

        # Call MatchmakingInterface callbacks
        if leading_str == BUTTON_PREFIX_JOIN:
            await matchmaker.callback_ready_game(ctx)
        elif leading_str == BUTTON_PREFIX_LEAVE:
            await matchmaker.callback_leave_game(ctx)
        elif leading_str == BUTTON_PREFIX_READY:
            await matchmaker.callback_toggle_ready(ctx)

    async def invite_accept_callback(self, ctx: discord.Interaction) -> None:
        """
        Invite accept button callback.
        """
        await ctx.response.defer()
        f_log = log.getChild("callback.invite_accept")

        data = ctx.data if ctx.data is not None else {}
        cid = data.get("custom_id")
        try:
            matchmaking_id = int(cid.replace(BUTTON_PREFIX_INVITE, ""))
        except (TypeError, ValueError, AttributeError):
            await followup_send(ctx, content=get("matchmaking.invalid_button"), ephemeral=True,
                                delete_after=EPHEMERAL_DELETE_AFTER)
            return

        if matchmaking_id not in CURRENT_MATCHMAKING:
            await followup_send(ctx,
                                content=get("matchmaking.invite_expired"),
                                ephemeral=True,
                                delete_after=EPHEMERAL_DELETE_AFTER,
                                )
            return

        matchmaker = CURRENT_MATCHMAKING[matchmaking_id]
        success = await matchmaker.accept_invite(ctx)

        if success:
            await followup_send(ctx, content=get("matchmaking.invite_ok"), ephemeral=True,
                                delete_after=EPHEMERAL_DELETE_AFTER)


async def setup(bot: commands.Bot):
    await bot.add_cog(MatchmakingCog(bot))
