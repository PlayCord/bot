import logging

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from configuration.constants import *
from utils import database as db, embeds as _embeds
from utils.analytics import Timer
from utils.discord_utils import decode_discord_arguments, format_user_error_message, send_simple_embed
from utils.emojis import get_emoji_string
from utils.interfaces import MatchmakingInterface, user_in_active_game
from utils.locale import fmt, get

CustomEmbed = _embeds.CustomEmbed

log = logging.getLogger(LOGGING_ROOT)


class GamesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_interaction(self, ctx: discord.Interaction) -> None:
        custom_id = ctx.data.get("custom_id")
        if custom_id is None:
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
        f_log = log.getChild("callback.game_button")
        leading_str = BUTTON_PREFIX_CURRENT_TURN if current_turn_required else BUTTON_PREFIX_NO_TURN
        data = ctx.data['custom_id'].replace(leading_str, "").split("/")
        game_id = int(data[0])
        function_id = data[1]
        arguments = {arg.split("=")[0]: arg.split("=")[1] for arg in data[2].split(",")} if data[2] else {}

        if game_id not in CURRENT_GAMES:
            await ctx.followup.send(
                content=format_user_error_message("game_ended"),
                ephemeral=True,
            )
            return

        game = CURRENT_GAMES[game_id]

        # Validate user is a participant in this game
        participant_ids = {p.id for p in game.players}
        if ctx.user.id not in participant_ids:
            await ctx.followup.send(PERMISSION_MSG_NOT_PARTICIPANT, ephemeral=True)
            return

        await game.move_by_button(ctx=ctx, name=function_id, arguments=arguments,
                                  current_turn_required=current_turn_required)

    async def game_select_callback(self, ctx: discord.Interaction, current_turn_required: bool = True) -> None:
        await ctx.response.defer()
        f_log = log.getChild("callback.game_select")
        leading_str = BUTTON_PREFIX_SELECT_CURRENT if current_turn_required else BUTTON_PREFIX_SELECT_NO_TURN
        data = ctx.data['custom_id'].replace(leading_str, "").split("/")
        game_id = int(data[0])
        function_id = data[1]
        arguments = {arg.split("=")[0]: arg.split("=")[1] for arg in data[2].split(",")} if len(data) > 2 and data[
            2] else {}
        arguments["values"] = ctx.data.get("values", [])

        if game_id not in CURRENT_GAMES:
            await ctx.followup.send(
                content=format_user_error_message("game_ended"),
                ephemeral=True,
            )
            return

        game = CURRENT_GAMES[game_id]

        # Validate user is a participant in this game
        participant_ids = {p.id for p in game.players}
        if ctx.user.id not in participant_ids:
            await ctx.followup.send(PERMISSION_MSG_NOT_PARTICIPANT, ephemeral=True)
            return

        await game.move_by_button(ctx=ctx, name=function_id, arguments=arguments,
                                  current_turn_required=current_turn_required)

    async def spectate_callback(self, ctx: discord.Interaction) -> None:
        await ctx.response.defer()
        f_log = log.getChild("callback.spectate")
        game_id = int(ctx.data['custom_id'].replace(BUTTON_PREFIX_SPECTATE, ""))
        if game_id not in CURRENT_GAMES:
            await ctx.followup.send(
                content=format_user_error_message("game_ended"),
                ephemeral=True,
            )
            return

        game = CURRENT_GAMES[game_id]

        # Check if user is already a participant (they're already in the thread)
        participant_ids = {p.id for p in game.players}
        if ctx.user.id in participant_ids:
            await ctx.followup.send(get("success.already_participant"), ephemeral=True)
            return

        # Check if spectating is allowed for this game (games can disable spectating)
        if hasattr(game.game, 'allow_spectating') and not game.game.allow_spectating:
            await ctx.followup.send(PERMISSION_MSG_SPECTATE_DISABLED, ephemeral=True)
            return

        await game.thread.add_user(ctx.user)
        await ctx.followup.send(get("success.spectating"), ephemeral=True)

    async def peek_callback(self, ctx: discord.Interaction) -> None:
        await ctx.response.defer()
        data = ctx.data['custom_id'].replace(BUTTON_PREFIX_PEEK, "").split("/")
        game_id, message_id = int(data[0]), int(data[1])
        if game_id in CURRENT_GAMES:
            # Just resend the latest game state to the user ephemerally
            await CURRENT_GAMES[game_id].display_game_state(ctx)
        else:
            await ctx.followup.send(
                content=format_user_error_message("game_ended"),
                ephemeral=True,
            )

    async def rematch_button_callback(self, ctx: discord.Interaction) -> None:
        await ctx.response.defer(ephemeral=True)
        from utils.models import MatchStatus

        tail = ctx.data["custom_id"].replace(BUTTON_PREFIX_REMATCH, "", 1)
        try:
            mid = int(tail)
        except ValueError:
            await ctx.followup.send(content=format_user_error_message("rematch_invalid"), ephemeral=True)
            return
        match = db.database.get_match(mid)
        if not match or match.status != MatchStatus.COMPLETED:
            await ctx.followup.send(content=format_user_error_message("rematch_unavailable"), ephemeral=True)
            return
        human_ids = db.database.get_match_human_user_ids_ordered(mid)
        if ctx.user.id not in human_ids:
            await ctx.followup.send(content=get("rematch.not_participant"), ephemeral=True)
            return
        for uid in human_ids:
            if user_in_active_game(uid):
                await ctx.followup.send(content=get("rematch.someone_busy"), ephemeral=True)
                return
        g = ctx.guild
        if g is None or not isinstance(ctx.channel, discord.TextChannel):
            await ctx.followup.send(content=get("rematch.bad_channel"), ephemeral=True)
            return
        game_row = db.database.get_game_by_id(match.game_id)
        if not game_row:
            await ctx.followup.send(content=get("rematch.unknown_game"), ephemeral=True)
            return
        game_type = game_row.game_name
        loading = await ctx.channel.send(embed=CustomEmbed(description=get_emoji_string("loading")).remove_footer())
        mm = MatchmakingInterface(ctx.user, game_type, loading, rated=match.is_rated, private=False)
        if mm.failed is not None:
            await loading.edit(embed=mm.failed)
            await ctx.followup.send(content=get("rematch.failed"), ephemeral=True)
            return
        err = await mm.seed_rematch_players(g, human_ids)
        if err:
            try:
                await loading.delete()
            except discord.HTTPException:
                pass
            await ctx.followup.send(content=err, ephemeral=True)
            return
        await mm.update_embed()
        await ctx.followup.send(content=get("rematch.created"), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GamesCog(bot))


async def begin_game(ctx: discord.Interaction, game_type: str, rated: bool = True,
                     private: bool = False) -> MatchmakingInterface | None:
    matchmaking_timer = Timer().start()
    f_log = log.getChild("command.matchmaking")
    if user_in_active_game(ctx.user.id):
        await send_simple_embed(
            ctx,
            title=get("begin_game.already_in_game_title"),
            description=get("begin_game.already_in_game_description"),
            ephemeral=True,
        )
        return None
    if not (ctx.channel.permissions_for(ctx.guild.me).create_private_threads and ctx.channel.permissions_for(
            ctx.guild.me).send_messages):
        await ctx.response.send_message(
            content=format_user_error_message("missing_permissions"),
            ephemeral=True,
        )
        return None
    if ctx.channel.type in [discord.ChannelType.public_thread, discord.ChannelType.private_thread]:
        await ctx.response.send_message(
            content=format_user_error_message("invalid_channel"),
            ephemeral=True,
        )
        return None

    require_pc = CONFIGURATION.get("playcord", {}).get("require_playcord_channel", False)
    if require_pc and ctx.guild is not None:
        pc = db.database.get_playcord_channel_id(ctx.guild.id)
        if pc is None:
            await ctx.response.send_message(
                content=format_user_error_message("playcord_channel_unset"),
                ephemeral=True,
            )
            return None
        if ctx.channel.id != pc:
            await ctx.response.send_message(
                content=fmt("playcord.wrong_channel", channel=f"<#{pc}>"),
                ephemeral=True,
            )
            return None

    await ctx.response.send_message(embed=CustomEmbed(description=get_emoji_string("loading")).remove_footer())
    game_overview_message = await ctx.original_response()
    interface = MatchmakingInterface(ctx.user, game_type, game_overview_message, rated=rated, private=private)
    if interface.failed is not None:
        await game_overview_message.edit(embed=interface.failed)
        return None
    await interface.update_embed()
    return interface


async def add_matchmaking_bot(ctx: discord.Interaction, difficulty: str) -> bool:
    async def _send(message: str) -> None:
        if ctx.response.is_done():
            await ctx.followup.send(message, ephemeral=True)
        else:
            await ctx.response.send_message(message, ephemeral=True)

    id_matchmaking = {p.id: q for p, q in IN_MATCHMAKING.items()}
    if ctx.user.id not in id_matchmaking:
        await _send(get("settings.not_in_matchmaking"))
        return False

    matchmaker: MatchmakingInterface = id_matchmaking[ctx.user.id]
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
    if ctx.channel.type != discord.ChannelType.private_thread:
        await send_simple_embed(
            ctx,
            get("move.invalid_context_title"),
            get("move.invalid_context_description"),
            ephemeral=True,
            responded=True
        )
        return
    if ctx.channel.id not in CURRENT_GAMES.keys():
        await send_simple_embed(
            ctx,
            get("move.invalid_context_title"),
            get("move.no_active_game_description"),
            ephemeral=True,
            responded=True
        )
        return
    arguments.pop("ctx")
    arguments = {a: await decode_discord_arguments(arguments[a]) for a in arguments.keys()}
    AUTOCOMPLETE_CACHE[ctx.channel.id] = {}
    await CURRENT_GAMES[ctx.channel.id].move_by_command(ctx, name, arguments,
                                                        current_turn_required=current_turn_required)


async def handle_autocomplete(ctx: discord.Interaction, function, current: str, argument) -> list[Choice[str]]:
    try:
        game_view = CURRENT_GAMES[ctx.channel.id]
    except KeyError:
        return [app_commands.Choice(name=get("autocomplete.no_game_in_channel"), value="")]
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

    valid_player_options = [[next(iter(o)), o[next(iter(o))]] for o in player_options if
                            current.lower() in next(iter(o)).lower()]
    final_autocomplete = sorted(valid_player_options, key=lambda x: x[0].lower().index(current.lower()))
    return [app_commands.Choice(name=ac_option[0], value=ac_option[1]) for ac_option in final_autocomplete]
