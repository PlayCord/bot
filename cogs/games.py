import asyncio
import logging

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from configuration.constants import (
    AUTOCOMPLETE_CACHE,
    BUTTON_PREFIX_CURRENT_TURN,
    BUTTON_PREFIX_NO_TURN,
    BUTTON_PREFIX_PAGINATION_FIRST,
    BUTTON_PREFIX_PAGINATION_LAST,
    BUTTON_PREFIX_PAGINATION_NEXT,
    BUTTON_PREFIX_PAGINATION_PREV,
    BUTTON_PREFIX_PEEK,
    BUTTON_PREFIX_REMATCH,
    BUTTON_PREFIX_SELECT_CURRENT,
    BUTTON_PREFIX_SELECT_NO_TURN,
    BUTTON_PREFIX_SPECTATE,
    CURRENT_GAMES,
    EPHEMERAL_DELETE_AFTER,
    LOGGING_ROOT,
    PERMISSION_MSG_NOT_PARTICIPANT,
    PERMISSION_MSG_SPECTATE_DISABLED,
)
from utils import database as db
from utils.containers import LoadingContainer, container_send_kwargs
from utils.discord_utils import (
    decode_discord_arguments,
    followup_send,
    format_user_error_message,
    response_send_message,
)
from utils.emojis import get_emoji_string
from utils.interfaces import MatchmakingInterface, user_in_active_game
from utils.matchmaking_user_map import matchmaking_by_user_id
from utils.locale import fmt, get

log = logging.getLogger(LOGGING_ROOT)


async def _send_game_ended_error(ctx: discord.Interaction) -> None:
    await followup_send(
        ctx,
        content=format_user_error_message("game_ended"),
        ephemeral=True,
        delete_after=EPHEMERAL_DELETE_AFTER,
    )


def _autocomplete_sort_key(label: str, current: str) -> tuple:
    lo, cu = label.lower(), current.lower()
    try:
        return (lo.index(cu), lo)
    except ValueError:
        return (0, lo)


_PAGINATION_PREFIXES = (
    BUTTON_PREFIX_PAGINATION_FIRST,
    BUTTON_PREFIX_PAGINATION_PREV,
    BUTTON_PREFIX_PAGINATION_NEXT,
    BUTTON_PREFIX_PAGINATION_LAST,
)


async def _pagination_unhandled_fallback(interaction: discord.Interaction, custom_id: str) -> None:
    """If no registered PaginationView handled the click (e.g. after restart), reply ephemerally."""
    await asyncio.sleep(0)
    if interaction.response.is_done():
        return
    rest = custom_id
    for prefix in _PAGINATION_PREFIXES:
        if custom_id.startswith(prefix):
            rest = custom_id[len(prefix):]
            break
    msg = get("interactions.pagination_outdated")
    parts = rest.split("/")
    if len(parts) == 2:
        try:
            gid, uid = int(parts[0]), int(parts[1])
        except ValueError:
            pass
        else:
            if interaction.user.id != uid:
                msg = get("interactions.pagination_not_yours")
            elif interaction.guild_id is not None and gid != interaction.guild_id:
                msg = get("interactions.pagination_not_yours")
    try:
        await response_send_message(interaction, msg, ephemeral=True, delete_after=EPHEMERAL_DELETE_AFTER)
    except discord.HTTPException:
        pass


class GamesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_interaction(self, ctx: discord.Interaction) -> None:
        data = ctx.data if ctx.data is not None else {}
        custom_id = data.get("custom_id")
        if custom_id is None:
            return

        if ctx.type is discord.InteractionType.component and any(
            custom_id.startswith(p) for p in _PAGINATION_PREFIXES
        ):
            asyncio.create_task(_pagination_unhandled_fallback(ctx, custom_id))
            return

        if custom_id.startswith(BUTTON_PREFIX_SELECT_CURRENT):
            await self.game_select_callback(ctx, current_turn_required=True)
        elif custom_id.startswith(BUTTON_PREFIX_SELECT_NO_TURN):
            await self.game_select_callback(ctx, current_turn_required=False)
        elif custom_id.startswith(BUTTON_PREFIX_CURRENT_TURN):
            await self.game_button_callback(ctx, current_turn_required=True)
        elif custom_id.startswith(BUTTON_PREFIX_NO_TURN):
            await self.game_button_callback(ctx, current_turn_required=False)
        elif custom_id.startswith(BUTTON_PREFIX_SPECTATE):
            await self.spectate_callback(ctx)
        elif custom_id.startswith(BUTTON_PREFIX_PEEK):
            await self.peek_callback(ctx)
        elif custom_id.startswith(BUTTON_PREFIX_REMATCH):
            await self.rematch_button_callback(ctx)

    async def game_button_callback(self, ctx: discord.Interaction, current_turn_required: bool = True) -> None:
        await ctx.response.defer()
        leading_str = BUTTON_PREFIX_CURRENT_TURN if current_turn_required else BUTTON_PREFIX_NO_TURN
        try:
            raw = ctx.data["custom_id"].replace(leading_str, "")
            data = raw.split("/")
            game_id = int(data[0])
            function_id = data[1]
            arg_blob = data[2] if len(data) > 2 else ""
            arguments = {arg.split("=")[0]: arg.split("=")[1] for arg in arg_blob.split(",") if "=" in arg} if arg_blob else {}
        except (KeyError, IndexError, ValueError):
            await _send_game_ended_error(ctx)
            return

        if game_id not in CURRENT_GAMES:
            await _send_game_ended_error(ctx)
            return

        game = CURRENT_GAMES[game_id]

        # Validate user is a participant in this game
        participant_ids = {p.id for p in game.players}
        if ctx.user.id not in participant_ids:
            await followup_send(ctx,
                PERMISSION_MSG_NOT_PARTICIPANT,
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        await game.move_by_button(ctx=ctx, name=function_id, arguments=arguments,
                                  current_turn_required=current_turn_required)

    async def game_select_callback(self, ctx: discord.Interaction, current_turn_required: bool = True) -> None:
        await ctx.response.defer()
        leading_str = BUTTON_PREFIX_SELECT_CURRENT if current_turn_required else BUTTON_PREFIX_SELECT_NO_TURN
        try:
            raw = ctx.data["custom_id"].replace(leading_str, "")
            data = raw.split("/")
            game_id = int(data[0])
            function_id = data[1]
        except (KeyError, IndexError, ValueError):
            await _send_game_ended_error(ctx)
            return

        if game_id not in CURRENT_GAMES:
            await _send_game_ended_error(ctx)
            return

        game = CURRENT_GAMES[game_id]

        # Validate user is a participant in this game
        participant_ids = {p.id for p in game.players}
        if ctx.user.id not in participant_ids:
            await followup_send(ctx,
                PERMISSION_MSG_NOT_PARTICIPANT,
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        await game.move_by_select(
            ctx=ctx, name=function_id, current_turn_required=current_turn_required
        )

    async def spectate_callback(self, ctx: discord.Interaction) -> None:
        await ctx.response.defer()
        try:
            game_id = int(ctx.data["custom_id"].replace(BUTTON_PREFIX_SPECTATE, ""))
        except (KeyError, ValueError):
            await _send_game_ended_error(ctx)
            return
        if game_id not in CURRENT_GAMES:
            await _send_game_ended_error(ctx)
            return

        game = CURRENT_GAMES[game_id]

        # Check if user is already a participant (they're already in the thread)
        participant_ids = {p.id for p in game.players}
        if ctx.user.id in participant_ids:
            await followup_send(ctx,
                get("success.already_participant"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        # Check if spectating is allowed for this game (games can disable spectating)
        if hasattr(game.game, 'allow_spectating') and not game.game.allow_spectating:
            await followup_send(ctx,
                PERMISSION_MSG_SPECTATE_DISABLED,
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        await game.thread.add_user(ctx.user)
        await followup_send(ctx, get("success.spectating"), ephemeral=True, delete_after=EPHEMERAL_DELETE_AFTER)

    async def peek_callback(self, ctx: discord.Interaction) -> None:
        await ctx.response.defer()
        try:
            data = ctx.data["custom_id"].replace(BUTTON_PREFIX_PEEK, "").split("/")
            game_id = int(data[0])
        except (KeyError, IndexError, ValueError):
            await _send_game_ended_error(ctx)
            return
        if game_id in CURRENT_GAMES:
            # Just resend the latest game state to the user ephemerally
            await CURRENT_GAMES[game_id].display_game_state(ctx)
        else:
            await _send_game_ended_error(ctx)

    async def rematch_button_callback(self, ctx: discord.Interaction) -> None:
        await ctx.response.defer(ephemeral=True)
        from utils.models import MatchStatus

        tail = ctx.data["custom_id"].replace(BUTTON_PREFIX_REMATCH, "", 1)
        try:
            mid = int(tail)
        except ValueError:
            await followup_send(ctx,content=format_user_error_message("rematch_invalid"), ephemeral=True)
            return
        match = db.database.get_match(mid)
        if not match or match.status != MatchStatus.COMPLETED:
            await followup_send(ctx,content=format_user_error_message("rematch_unavailable"), ephemeral=True)
            return
        human_ids = db.database.get_match_human_user_ids_ordered(mid)
        if ctx.user.id not in human_ids:
            await followup_send(ctx,content=get("rematch.not_participant"), ephemeral=True)
            return
        for uid in human_ids:
            if user_in_active_game(uid):
                await followup_send(ctx,content=get("rematch.someone_busy"), ephemeral=True)
                return
        g = ctx.guild
        if g is None or not isinstance(ctx.channel, discord.TextChannel):
            await followup_send(ctx,content=get("rematch.bad_channel"), ephemeral=True)
            return
        game_row = db.database.get_game_by_id(match.game_id)
        if not game_row:
            await followup_send(ctx,content=get("rematch.unknown_game"), ephemeral=True)
            return
        game_type = game_row.game_name
        loading = await ctx.channel.send(**container_send_kwargs(LoadingContainer(message=get_emoji_string("loading")).remove_footer()))
        mm = MatchmakingInterface(ctx.user, game_type, loading, rated=match.is_rated, private=False)
        if mm.failed is not None:
            await loading.edit(content=str(mm.failed), view=None, attachments=[])
            await followup_send(ctx,content=get("rematch.failed"), ephemeral=True)
            return
        err = await mm.seed_rematch_players(g, human_ids)
        if err:
            try:
                await loading.delete()
            except discord.HTTPException:
                pass
            await followup_send(ctx,content=err, ephemeral=True)
            return
        await mm.update_embed()
        await followup_send(ctx,content=get("rematch.created"), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GamesCog(bot))


async def begin_game(ctx: discord.Interaction, game_type: str, rated: bool = True,
                     private: bool = False) -> MatchmakingInterface | None:
    f_log = log.getChild("command.matchmaking")
    if user_in_active_game(ctx.user.id):
        await response_send_message(
            ctx,
            content=get("begin_game.already_in_game_description"),
            ephemeral=True,
            delete_after=EPHEMERAL_DELETE_AFTER,
        )
        return None
    me = ctx.guild.me
    channel_perms = ctx.channel.permissions_for(me)
    if not (channel_perms.create_private_threads and channel_perms.send_messages):
        await response_send_message(
            ctx,
            content=format_user_error_message("missing_permissions"),
            ephemeral=True,
        )
        return None
    if ctx.channel.type in [discord.ChannelType.public_thread, discord.ChannelType.private_thread]:
        await response_send_message(
            ctx,
            content=format_user_error_message("invalid_channel"),
            ephemeral=True,
        )
        return None

    if ctx.guild is not None:
        pc = db.database.get_playcord_channel_id(ctx.guild.id)
        if pc is not None and ctx.channel.id != pc:
            await response_send_message(
                ctx,
                content=fmt("playcord.wrong_channel", channel=f"<#{pc}>"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return None

    await response_send_message(
        ctx,
        **container_send_kwargs(LoadingContainer(message=get_emoji_string("loading")).remove_footer()),
    )
    game_overview_message = await ctx.original_response()
    try:
        interface = MatchmakingInterface(ctx.user, game_type, game_overview_message, rated=rated, private=private)
        if interface.failed is not None:
            await game_overview_message.edit(content=str(interface.failed), view=None, attachments=[])
            return None
        await interface.update_embed()
        from utils.analytics import EventType, register_event

        register_event(
            EventType.MATCHMAKING_STARTED,
            user_id=ctx.user.id,
            guild_id=ctx.guild.id if ctx.guild else None,
            game_type=game_type,
            metadata={"lobby_message_id": game_overview_message.id},
        )
        return interface
    except Exception:
        f_log.exception("begin_game failed for game_type=%r", game_type)
        try:
            await game_overview_message.edit(
                content=get("system_error.internal_what_failed"),
                view=None,
                attachments=[],
            )
        except Exception:
            pass
        return None


async def add_matchmaking_bot(ctx: discord.Interaction, difficulty: str) -> bool:
    async def _send(message: str) -> None:
        if ctx.response.is_done():
            await followup_send(ctx, message, ephemeral=True)
        else:
            await response_send_message(ctx, message, ephemeral=True)

    mm_by_user = matchmaking_by_user_id()
    if ctx.user.id not in mm_by_user:
        await _send(get("settings.not_in_matchmaking"))
        return False

    matchmaker: MatchmakingInterface = mm_by_user[ctx.user.id]
    if matchmaker.creator.id != ctx.user.id:
        await _send(get("settings.only_creator"))
        return False

    is_matchmaker_rated = matchmaker.rated
    result = matchmaker.add_bot(difficulty)
    if result is not None:
        await _send(result)
        return False

    await matchmaker.update_embed()
    if is_matchmaker_rated:  # Only send warning if it actually changed something
        await _send(get("queue.bot_rated_forced"))
    return True


async def handle_move(ctx: discord.Interaction, name, arguments, current_turn_required: bool = True) -> None:
    from utils.analytics import EventType, register_event

    requested_group = getattr(getattr(getattr(ctx, "command", None), "parent", None), "name", None)

    def _track_move_rejected(reason: str, *, game_type: str | None = None, match_id: int | None = None) -> None:
        register_event(
            EventType.MOVE_REJECTED,
            user_id=getattr(getattr(ctx, "user", None), "id", None),
            guild_id=ctx.guild.id if getattr(ctx, "guild", None) else None,
            game_type=game_type or requested_group,
            match_id=match_id,
            metadata={
                "reason": reason,
                "move_name": name,
                "command_group": requested_group,
                "current_turn_required": bool(current_turn_required),
                "source": "handle_move",
            },
        )

    if ctx.channel.type != discord.ChannelType.private_thread:
        _track_move_rejected("wrong_channel")
        await followup_send(
            ctx,
            content=f"{get('move.invalid_context_title')}. {get('move.invalid_context_description')}",
            ephemeral=True,
            delete_after=EPHEMERAL_DELETE_AFTER,
        )
        return
    if ctx.channel.id not in CURRENT_GAMES:
        _track_move_rejected("no_active_game")
        await followup_send(
            ctx,
            content=f"{get('move.invalid_context_title')}. {get('move.no_active_game_description')}",
            ephemeral=True,
            delete_after=EPHEMERAL_DELETE_AFTER,
        )
        return
    active_game = CURRENT_GAMES[ctx.channel.id]
    command_parent = getattr(getattr(ctx, "command", None), "parent", None)
    requested_game_type = getattr(command_parent, "name", None)
    if requested_game_type and requested_game_type != active_game.game_type:
        _track_move_rejected(
            "wrong_game_type",
            game_type=active_game.game_type,
            match_id=getattr(active_game, "game_id", None),
        )
        await followup_send(
            ctx,
            content=(
                f"{get('move.invalid_context_title')}. "
                f"{fmt('move.wrong_game_type_description', game=active_game.game_type)}"
            ),
            ephemeral=True,
            delete_after=EPHEMERAL_DELETE_AFTER,
        )
        return
    arguments.pop("ctx")
    arguments = {a: await decode_discord_arguments(arguments[a]) for a in arguments}
    AUTOCOMPLETE_CACHE[ctx.channel.id] = {}
    await active_game.move_by_command(ctx, name, arguments, current_turn_required=current_turn_required)


async def handle_autocomplete(ctx: discord.Interaction, function, current: str, argument) -> list[Choice[str]]:
    try:
        game_view = CURRENT_GAMES[ctx.channel.id]
    except KeyError:
        return [app_commands.Choice(name=get("autocomplete.no_game_in_channel"), value="")]
    if game_view.game.is_game_finished():
        return [app_commands.Choice(name=get("autocomplete.game_finished"), value="-")]
    player = db.database.get_player(ctx.user, ctx.guild.id)
    try:
        player_options = AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id][function][argument][current]
    except KeyError:
        ac_callback = None
        matched_option = None
        for move in game_view.game.moves:
            if move.options is None: continue
            for option in move.options:
                if option.name == argument:
                    ac_callback = getattr(game_view.game, option.autocomplete, None)
                    matched_option = option
                    break
            if matched_option is not None: break
        if matched_option is None or ac_callback is None:
            return [app_commands.Choice(name=get("autocomplete.function_missing"), value="")]
        if not matched_option.force_reload:
            player_options = ac_callback(player)
            if ctx.channel.id not in AUTOCOMPLETE_CACHE: AUTOCOMPLETE_CACHE[ctx.channel.id] = {}
            if ctx.user.id not in AUTOCOMPLETE_CACHE[ctx.channel.id]: AUTOCOMPLETE_CACHE[ctx.channel.id][
                ctx.user.id] = {}
            if function not in AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id]:
                AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id][function] = {}
            if argument not in AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id][function]:
                AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id][function][argument] = {}
                AUTOCOMPLETE_CACHE[ctx.channel.id][ctx.user.id][function][argument].update({current: player_options})
        else:
            player_options = ac_callback(player)

    valid_player_options = []
    for o in player_options:
        if not o:
            continue
        label, value = next(iter(o.items()))
        if current.lower() in label.lower():
            valid_player_options.append([label, value])
    final_autocomplete = sorted(valid_player_options, key=lambda x: _autocomplete_sort_key(x[0], current))
    return [app_commands.Choice(name=ac_option[0], value=ac_option[1]) for ac_option in final_autocomplete]
