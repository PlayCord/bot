from typing import Any

import discord
from discord.ext import commands

from playcord.infrastructure.constants import (
    BUTTON_PREFIX_INVITE,
    BUTTON_PREFIX_JOIN,
    BUTTON_PREFIX_LEAVE,
    BUTTON_PREFIX_LOBBY_ASSIGN_ROLES,
    BUTTON_PREFIX_LOBBY_OPT,
    BUTTON_PREFIX_LOBBY_ROLE,
    BUTTON_PREFIX_LOBBY_SETTINGS,
    BUTTON_PREFIX_LOBBY_SETTINGS_END,
    BUTTON_PREFIX_LOBBY_SETTINGS_PRIV,
    BUTTON_PREFIX_LOBBY_SETTINGS_RESET_PRIV,
    BUTTON_PREFIX_LOBBY_SETTINGS_RESET_RULES,
    BUTTON_PREFIX_READY,
    EPHEMERAL_DELETE_AFTER,
)
from playcord.infrastructure.locale import get
from playcord.infrastructure.logging import get_logger
from playcord.presentation.interactions.contextify import contextify
from playcord.presentation.interactions.helpers import followup_send

log = get_logger()


class MatchmakingCog(commands.Cog):
    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot

    @property
    def _lobbies(self) -> dict[int, Any]:
        return self.bot.container.registry.matchmaking_by_lobby_key

    async def _send_matchmaking_error(self, ctx: discord.Interaction, message_key: str) -> None:
        await followup_send(
            ctx,
            content=get(message_key),
            ephemeral=True,
            delete_after=EPHEMERAL_DELETE_AFTER,
        )

    async def _require_lobby_key(
        self,
        ctx: discord.Interaction,
        *,
        custom_id: str | None,
        prefix: str,
        log_child: str,
    ) -> int | None:
        f_log = log.getChild(log_child)
        if not custom_id or not custom_id.startswith(prefix):
            f_log.warning(
                "Invalid lobby interaction from user=%s cid=%r",
                getattr(ctx.user, "id", None),
                custom_id,
            )
            await self._send_matchmaking_error(ctx, "matchmaking.invalid_interaction")
            return None
        lobby_key_str = custom_id[len(prefix) :].partition("/")[0].rstrip("/")
        if not lobby_key_str:
            await self._send_matchmaking_error(ctx, "matchmaking.invalid_button")
            return None
        try:
            lobby_key = int(lobby_key_str)
        except ValueError:
            f_log.warning(
                "Invalid lobby key from user=%s lobby_key=%r",
                getattr(ctx.user, "id", None),
                lobby_key_str,
            )
            await self._send_matchmaking_error(ctx, "matchmaking.invalid_button")
            return None
        if lobby_key not in self._lobbies:
            f_log.info(
                "Expired lobby interaction lobby_key=%s user=%s",
                lobby_key,
                getattr(ctx.user, "id", None),
            )
            await self._send_matchmaking_error(ctx, "matchmaking.session_expired")
            return None
        return lobby_key

    # No specific commands here yet as they are mostly subcommands of playcord or play
    # But we can store callbacks here

    @commands.Cog.listener()
    async def on_interaction(self, ctx: discord.Interaction) -> None:
        """Callback activated after every bot interaction."""
        data = ctx.data if ctx.data is not None else {}
        custom_id = data.get("custom_id")
        if custom_id is None:
            return

        log.getChild("on_interaction").debug(
            "on_interaction custom_id=%r user=%s",
            custom_id,
            getattr(ctx.user, "id", None),
        )

        if custom_id.startswith(BUTTON_PREFIX_LOBBY_OPT):
            await self.lobby_select_callback(ctx)
        elif custom_id.startswith(BUTTON_PREFIX_LOBBY_ROLE):
            await self.lobby_role_select_callback(ctx)
        elif custom_id.startswith(BUTTON_PREFIX_LOBBY_ASSIGN_ROLES):
            await self.lobby_assign_roles_callback(ctx)
        elif custom_id.startswith(BUTTON_PREFIX_LOBBY_SETTINGS):
            await self.lobby_settings_callback(ctx)
        elif custom_id.startswith(BUTTON_PREFIX_LOBBY_SETTINGS_PRIV):
            await self.lobby_settings_privacy_callback(ctx)
        elif custom_id.startswith(BUTTON_PREFIX_LOBBY_SETTINGS_RESET_PRIV):
            await self.lobby_settings_reset_privacy_callback(ctx)
        elif custom_id.startswith(BUTTON_PREFIX_LOBBY_SETTINGS_RESET_RULES):
            await self.lobby_settings_reset_rules_callback(ctx)
        elif custom_id.startswith(BUTTON_PREFIX_LOBBY_SETTINGS_END):
            await self.lobby_settings_end_callback(ctx)
        elif custom_id.startswith(
            (BUTTON_PREFIX_JOIN, BUTTON_PREFIX_LEAVE, BUTTON_PREFIX_READY),
        ):
            await self.matchmaking_button_callback(ctx)
        elif custom_id.startswith(BUTTON_PREFIX_INVITE):
            await self.invite_accept_callback(ctx)

    async def lobby_select_callback(self, ctx: discord.Interaction) -> None:
        """
        Lobby string-select for per-game
        match options (handled by MatchmakingInterface).
        """
        await ctx.response.defer(ephemeral=True)
        f_log = log.getChild("callback.lobby_select")
        f_log.debug(
            "lobby_select_callback called by user=%s data=%r",
            getattr(ctx.user, "id", None),
            ctx.data,
        )
        data = ctx.data if ctx.data is not None else {}
        cid = data.get("custom_id")
        if not cid or not cid.startswith(BUTTON_PREFIX_LOBBY_OPT):
            f_log.warning(
                "Invalid lobby_select interaction from user=%s cid=%r",
                getattr(ctx.user, "id", None),
                cid,
            )
            await followup_send(
                ctx,
                content=get("matchmaking.invalid_interaction"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        rest = cid[len(BUTTON_PREFIX_LOBBY_OPT) :]
        lobby_key_str, _, key = rest.partition("/")
        if not lobby_key_str or not key:
            await followup_send(
                ctx,
                content=get("matchmaking.invalid_button"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        try:
            lobby_key = int(lobby_key_str)
        except ValueError:
            f_log.warning(
                "Invalid lobby key in lobby_select from user=%s lobby_key=%r",
                getattr(ctx.user, "id", None),
                lobby_key_str,
            )
            await followup_send(
                ctx,
                content=get("matchmaking.invalid_button"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        if lobby_key not in self._lobbies:
            f_log.info(
                "Lobby select for expired lobby_key=%s by user=%s",
                lobby_key,
                getattr(ctx.user, "id", None),
            )
            await followup_send(
                ctx,
                content=get("matchmaking.session_expired"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        f_log.debug(
            "lobby option key=%r lobby=%s user=%s",
            key,
            lobby_key,
            ctx.user.id,
        )
        matchmaker = self._lobbies[lobby_key]
        await matchmaker.callback_lobby_option(ctx, key)

    async def lobby_role_select_callback(self, ctx: discord.Interaction) -> None:
        """
        Per-player role select for
        CHOSEN :attr:`role_mode` (handled by MatchmakingInterface).
        """
        await ctx.response.defer(ephemeral=True)
        f_log = log.getChild("callback.lobby_role_select")
        f_log.debug(
            "lobby_role_select_callback called by user=%s data=%r",
            getattr(ctx.user, "id", None),
            ctx.data,
        )
        data = ctx.data if ctx.data is not None else {}
        cid = data.get("custom_id")
        if not cid or not cid.startswith(BUTTON_PREFIX_LOBBY_ROLE):
            f_log.warning(
                "Invalid lobby_role_select interaction from user=%s cid=%r",
                getattr(ctx.user, "id", None),
                cid,
            )
            await followup_send(
                ctx,
                content=get("matchmaking.invalid_interaction"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        rest = cid[len(BUTTON_PREFIX_LOBBY_ROLE) :]
        lobby_key_str, _, pid_str = rest.partition("/")
        if not lobby_key_str or not pid_str:
            await followup_send(
                ctx,
                content=get("matchmaking.invalid_button"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        try:
            lobby_key = int(lobby_key_str)
            player_id = int(pid_str)
        except ValueError:
            f_log.warning(
                "Invalid ids in lobby_role_select from user=%s lobby_key=%r pid=%r",
                getattr(ctx.user, "id", None),
                lobby_key_str,
                pid_str,
            )
            await followup_send(
                ctx,
                content=get("matchmaking.invalid_button"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        if lobby_key not in self._lobbies:
            f_log.info(
                "Lobby role select for expired lobby_key=%s by user=%s",
                lobby_key,
                getattr(ctx.user, "id", None),
            )
            await followup_send(
                ctx,
                content=get("matchmaking.session_expired"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        f_log.debug(
            "lobby role pick lobby=%s player_id=%s user=%s",
            lobby_key,
            player_id,
            ctx.user.id,
        )
        matchmaker = self._lobbies[lobby_key]
        await matchmaker.callback_role_select(ctx, player_id)

    async def lobby_assign_roles_callback(self, ctx: discord.Interaction) -> None:
        """Assign roles button for selectable_random flow."""
        await ctx.response.defer(ephemeral=True)
        f_log = log.getChild("callback.lobby_assign_roles")
        data = ctx.data if ctx.data is not None else {}
        lobby_key = await self._require_lobby_key(
            ctx,
            custom_id=data.get("custom_id"),
            prefix=BUTTON_PREFIX_LOBBY_ASSIGN_ROLES,
            log_child="callback.lobby_assign_roles",
        )
        if lobby_key is None:
            return
        f_log.debug(
            "lobby assign roles lobby=%s user=%s",
            lobby_key,
            ctx.user.id,
        )
        await self._lobbies[lobby_key].callback_assign_roles(ctx)

    async def lobby_settings_callback(self, ctx: discord.Interaction) -> None:
        """Settings button — opens the settings modal for the lobby creator."""
        await self._lobby_settings_action(
            ctx,
            prefix=BUTTON_PREFIX_LOBBY_SETTINGS,
            log_name="callback.lobby_settings",
            handler_name="callback_lobby_settings",
        )

    async def lobby_settings_privacy_callback(self, ctx: discord.Interaction) -> None:
        """Privacy select in the ephemeral lobby settings panel."""
        await self._lobby_settings_action(
            ctx,
            prefix=BUTTON_PREFIX_LOBBY_SETTINGS_PRIV,
            log_name="callback.lobby_settings_privacy",
            handler_name="callback_lobby_privacy",
        )

    async def _lobby_settings_action(
        self,
        ctx: discord.Interaction,
        *,
        prefix: str,
        log_name: str,
        handler_name: str,
    ) -> None:
        await ctx.response.defer(ephemeral=True)
        data = ctx.data if ctx.data is not None else {}
        lobby_key = await self._require_lobby_key(
            ctx,
            custom_id=data.get("custom_id"),
            prefix=prefix,
            log_child=log_name,
        )
        if lobby_key is None:
            return
        matchmaker = self._lobbies[lobby_key]
        await getattr(matchmaker, handler_name)(ctx)

    async def lobby_settings_reset_privacy_callback(self, ctx: discord.Interaction) -> None:
        """Reset privacy to defaults."""
        await self._lobby_settings_action(
            ctx,
            prefix=BUTTON_PREFIX_LOBBY_SETTINGS_RESET_PRIV,
            log_name="callback.lobby_settings_reset_privacy",
            handler_name="callback_lobby_reset_privacy",
        )

    async def lobby_settings_reset_rules_callback(self, ctx: discord.Interaction) -> None:
        """Reset game rules to defaults."""
        await self._lobby_settings_action(
            ctx,
            prefix=BUTTON_PREFIX_LOBBY_SETTINGS_RESET_RULES,
            log_name="callback.lobby_settings_reset_rules",
            handler_name="callback_lobby_reset_rules",
        )

    async def lobby_settings_end_callback(self, ctx: discord.Interaction) -> None:
        """End the lobby from settings."""
        await self._lobby_settings_action(
            ctx,
            prefix=BUTTON_PREFIX_LOBBY_SETTINGS_END,
            log_name="callback.lobby_settings_end",
            handler_name="callback_lobby_end_game",
        )

    async def matchmaking_button_callback(self, ctx: discord.Interaction) -> None:
        """Handle matchmaking button (Join / Leave / Ready)."""
        await ctx.response.defer()
        f_log = log.getChild("callback.matchmaking_button")

        data = ctx.data if ctx.data is not None else {}
        cid = data.get("custom_id")
        if not cid:
            f_log.warning(
                "Empty custom_id in matchmaking_button callback from user=%s",
                getattr(ctx.user, "id", None),
            )
            await followup_send(
                ctx,
                content=get("matchmaking.invalid_interaction"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        # Get interaction context
        interaction_context = contextify(ctx)
        f_log.info(
            f"matchmaking button pressed! ID: {cid} context: {interaction_context}",
        )
        f_log.debug(
            "matchmaking_button cid=%r user=%s",
            cid,
            getattr(ctx.user, "id", None),
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
            lobby_key = int(cid.replace(leading_str, ""))
        except ValueError:
            f_log.warning(
                "Invalid lobby key in button callback from user=%s cid=%r",
                getattr(ctx.user, "id", None),
                cid,
            )
            await followup_send(
                ctx,
                content=get("matchmaking.invalid_button"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        # Check if it exists
        if lobby_key not in self._lobbies:
            f_log.debug(
                "Matchmaking expired when trying to press button: %s",
                interaction_context,
            )
            await followup_send(
                ctx,
                content=get("matchmaking.session_expired"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        matchmaker = self._lobbies[lobby_key]

        # Call MatchmakingInterface callbacks
        if leading_str == BUTTON_PREFIX_JOIN:
            f_log.info(
                "Invoking callback_ready_game for lobby_key=%s user=%s",
                lobby_key,
                getattr(ctx.user, "id", None),
            )
            await matchmaker.callback_ready_game(ctx)
        elif leading_str == BUTTON_PREFIX_LEAVE:
            f_log.info(
                "Invoking callback_leave_game for lobby_key=%s user=%s",
                lobby_key,
                getattr(ctx.user, "id", None),
            )
            await matchmaker.callback_leave_game(ctx)
        elif leading_str == BUTTON_PREFIX_READY:
            f_log.info(
                "Invoking callback_toggle_ready for lobby_key=%s user=%s",
                lobby_key,
                getattr(ctx.user, "id", None),
            )
            await matchmaker.callback_toggle_ready(ctx)

    async def invite_accept_callback(self, ctx: discord.Interaction) -> None:
        """Invite accept button callback."""
        await ctx.response.defer()
        f_log = log.getChild("callback.invite_accept")
        f_log.debug(
            "invite_accept_callback called by user=%s data=%r",
            getattr(ctx.user, "id", None),
            ctx.data,
        )

        data = ctx.data if ctx.data is not None else {}
        cid = data.get("custom_id")
        try:
            lobby_key = int(cid.replace(BUTTON_PREFIX_INVITE, ""))
        except (TypeError, ValueError, AttributeError):
            f_log.warning(
                "Invalid invite custom_id from user=%s cid=%r",
                getattr(ctx.user, "id", None),
                cid,
            )
            await followup_send(
                ctx,
                content=get("matchmaking.invalid_button"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        if lobby_key not in self._lobbies:
            await followup_send(
                ctx,
                content=get("matchmaking.invite_expired"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        matchmaker = self._lobbies[lobby_key]
        success = await matchmaker.accept_invite(ctx)

        if success:
            f_log.info(
                "Invite accepted for lobby_key=%s by user=%s",
                lobby_key,
                getattr(ctx.user, "id", None),
            )
            await followup_send(
                ctx,
                content=get("matchmaking.invite_ok"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MatchmakingCog(bot))
