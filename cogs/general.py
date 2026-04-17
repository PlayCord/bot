import importlib
from datetime import datetime
from difflib import get_close_matches

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from api.Game import resolve_player_count
from configuration.constants import (
    BUTTON_PREFIX_INVITE,
    CATALOG_GAMES_PER_PAGE,
    CURRENT_GAMES,
    EPHEMERAL_DELETE_AFTER,
    GAME_TYPES,
    HELP_GAMES_PREVIEW_COUNT,
    HISTORY_PAGE_SIZE,
    INFO_COLOR,
    IN_GAME,
    IN_MATCHMAKING,
    LEADERBOARD_PAGE_SIZE,
    LOGGING_ROOT,
    MANAGED_BY,
    MU,
    NAME,
    VERSION,
)
from utils import database as db, ramcheck
from utils.containers import (
    CustomContainer,
    HelpCommandsContainer,
    HelpFaqContainer,
    HelpGettingStartedContainer,
    HelpMainContainer,
    HelpTutorialsContainer,
    InviteContainer,
    TEXT_DISPLAY_MAX,
    container_send_kwargs,
    container_to_markdown,
)
from utils.conversion import contextify
from utils.discord_utils import (
    followup_send,
    format_user_error_message,
    interaction_check,
    response_send_message,
)
from utils.emojis import get_emoji_string, get_game_emoji
from utils.graphs import generate_elo_chart
from utils.interfaces import user_in_active_game
from utils.matchmaking_interface import MatchmakingInterface
from utils.locale import fmt, get, plural
from utils.logging_config import get_logger
from utils.matchmaking_user_map import matchmaking_by_user_id
from utils.replay_format import chunk_replay_lines, format_replay_event_line
from utils.views import HelpView, InviteView, PaginationView

log = get_logger()

_GAME_METADATA: dict[str, dict] = {}


def _load_game_metadata() -> None:
    """Populate game class metadata once at import (avoids importlib per autocomplete keystroke)."""
    global _GAME_METADATA
    _GAME_METADATA = {}
    for gid, (mod_name, cls_name) in GAME_TYPES.items():
        game_class = getattr(importlib.import_module(mod_name), cls_name)
        _GAME_METADATA[gid] = {
            "class": game_class,
            "name": getattr(game_class, "name", gid),
            "summary": getattr(game_class, "summary", None),
            "description": getattr(game_class, "description", ""),
            "time": getattr(game_class, "time", None),
            "difficulty": getattr(game_class, "difficulty", None),
        }


_load_game_metadata()


def _ordinal(value: int) -> str:
    if value is None:
        return "?"
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def _resolve_game_id_input(raw: str) -> tuple[str | None, str | None]:
    selected = (raw or "").strip()
    game_type = selected.lower()
    if game_type in GAME_TYPES:
        return game_type, None

    candidates = get_close_matches(game_type, list(GAME_TYPES), n=1, cutoff=0.55)
    if candidates:
        return None, candidates[0]
    return None, None


def _history_status_label(status: str | None) -> str:
    status_map = {
        "completed": "completed",
        "interrupted": "interrupted",
        "abandoned": "abandoned",
    }
    return status_map.get((status or "").lower(), "completed")


def resolve_match_for_replay(raw: str, guild_id: int):
    """Resolve a match from an 8-char public code or a numeric ``match_id`` (guild-scoped)."""
    from utils.match_codes import is_match_code_token

    s = (raw or "").strip().lower()
    if not s:
        return None
    if is_match_code_token(s):
        m = db.database.get_match_by_code(s)
        if m is not None and m.guild_id == guild_id:
            return m
        if s.isdigit():
            m2 = db.database.get_match(int(s))
            if m2 is not None and m2.guild_id == guild_id:
                return m2
        return None
    if s.isdigit():
        m = db.database.get_match(int(s))
        if m is not None and m.guild_id == guild_id:
            return m
    return None


async def autocomplete_game_id(
    ctx: discord.Interaction, current: str
) -> list[Choice[str]]:
    query = current.lower().strip()
    matches = []

    for game_id, meta in _GAME_METADATA.items():
        summary = meta["summary"]
        description = str(summary) if summary is not None else ""
        if description:
            description = " (" + description + ")"
        display_name = str(meta["name"]) + description

        searchable = f"{game_id} {display_name}".lower()
        if query and query not in searchable:
            continue

        if query and game_id.lower().startswith(query):
            rank = 0
        elif query and display_name.lower().startswith(query):
            rank = 1
        else:
            rank = 2
        matches.append((rank, game_id.lower(), display_name, game_id))

    if query and not matches:
        fuzzy = get_close_matches(query, list(_GAME_METADATA), n=25, cutoff=0.4)
        for game_id in fuzzy:
            meta = _GAME_METADATA[game_id]
            summary = meta["summary"]
            description = str(summary) if summary is not None else ""
            if description:
                description = " (" + description + ")"
            display_name = str(meta["name"]) + description
            matches.append((3, game_id.lower(), display_name, game_id))

    matches.sort(key=lambda item: (item[0], item[1]))
    return [Choice(name=name[:100], value=value) for _, _, name, value in matches[:25]]


@app_commands.command(name="play", description=get("commands.play.description"))
@app_commands.describe(
    game=get("commands.play.param_game"),
    rated=get("commands.settings.param_rated"),
    private=get("commands.settings.param_private"),
)
@app_commands.autocomplete(game=autocomplete_game_id)
@app_commands.guild_only()
@app_commands.check(interaction_check)
async def command_play(
    ctx: discord.Interaction, game: str, rated: bool = True, private: bool = False
) -> None:
    f_log = log.getChild("command.play")
    f_log.debug(
        "/play called by user=%s game=%r rated=%s private=%s",
        getattr(ctx.user, "id", None),
        game,
        rated,
        private,
    )
    selected_game = game.strip()
    game_type, suggestion = _resolve_game_id_input(selected_game)
    if game_type is None:
        message = format_user_error_message("game_invalid", game=selected_game)
        if suggestion:
            message = (
                f"{message}\n\n{fmt('commands.play.did_you_mean', game=suggestion)}"
            )
        await response_send_message(
            ctx,
            content=message,
            ephemeral=True,
            delete_after=EPHEMERAL_DELETE_AFTER,
        )
        return

    from cogs.games import begin_game

    await begin_game(ctx, game_type, rated=rated, private=private)


async def autocomplete_invite_bot(
    ctx: discord.Interaction, current: str
) -> list[Choice[str]]:
    if user_in_active_game(ctx.user.id):
        return []

    mm_by_user = matchmaking_by_user_id()
    if ctx.user.id not in mm_by_user:
        return []

    matchmaker: MatchmakingInterface = mm_by_user[ctx.user.id]
    available_bots = getattr(matchmaker.game, "bots", {})
    if not available_bots:
        return []

    query = current.lower().strip()
    matches = []
    for difficulty, bot in available_bots.items():
        description = getattr(bot, "description", "")
        label = (
            f"{difficulty.title()} ({description})"
            if description
            else difficulty.title()
        )
        searchable = f"{difficulty} {description}".lower()

        if query and query not in searchable and query not in label.lower():
            continue

        rank = 0 if query and difficulty.lower().startswith(query) else 1
        matches.append((rank, difficulty.lower(), label, difficulty))

    matches.sort(key=lambda item: (item[0], item[1]))
    return [Choice(name=name[:100], value=value) for _, _, name, value in matches[:25]]


class GeneralCog(commands.Cog):
    def __init__(self, bot: discord.Client):
        self.bot = bot

    command_root = app_commands.Group(
        name=LOGGING_ROOT,
        description=get("commands.group.description"),
        guild_only=False,
    )

    @command_root.command(name="invite", description=get("commands.invite.description"))
    @app_commands.check(interaction_check)
    @app_commands.describe(
        game=get("commands.invite.param_game"),
        user=get("commands.invite.param_user"),
        user2=get("commands.invite.param_user2"),
        user3=get("commands.invite.param_user3"),
        user4=get("commands.invite.param_user4"),
        user5=get("commands.invite.param_user5"),
        bot=get("commands.invite.param_bot1"),
        bot2=get("commands.invite.param_bot2"),
        bot3=get("commands.invite.param_bot3"),
        bot4=get("commands.invite.param_bot4"),
        bot5=get("commands.invite.param_bot5"),
    )
    @app_commands.autocomplete(
        game=autocomplete_game_id,
        bot=autocomplete_invite_bot,
        bot2=autocomplete_invite_bot,
        bot3=autocomplete_invite_bot,
        bot4=autocomplete_invite_bot,
        bot5=autocomplete_invite_bot,
    )
    async def command_invite(
        self,
        ctx: discord.Interaction,
        game: str = None,
        user: discord.User = None,
        user2: discord.User = None,
        user3: discord.User = None,
        user4: discord.User = None,
        user5: discord.User = None,
        bot: str = None,
        bot2: str = None,
        bot3: str = None,
        bot4: str = None,
        bot5: str = None,
    ) -> None:
        f_log = log.getChild("command.invite")
        f_log.debug(f"/invite called: {contextify(ctx)}")
        invited_users = [
            candidate
            for candidate in [user, user2, user3, user4, user5]
            if candidate is not None
        ]
        requested_bots = [
            candidate
            for candidate in [bot, bot2, bot3, bot4, bot5]
            if candidate is not None
        ]
        f_log.debug(
            "Invite targets: users=%s bots=%s",
            [getattr(u, "id", str(u)) for u in invited_users],
            requested_bots,
        )

        if not invited_users and not requested_bots:
            if ctx.response.is_done():
                await followup_send(
                    ctx, get("matchmaking.invite_no_targets"), ephemeral=True
                )
            else:
                await response_send_message(
                    ctx, get("matchmaking.invite_no_targets"), ephemeral=True
                )
            return

        mm_by_user = matchmaking_by_user_id()

        if ctx.user.id not in mm_by_user:
            if user_in_active_game(ctx.user.id):
                await response_send_message(
                    ctx,
                    content=format_user_error_message("already_in_game_other_server"),
                    ephemeral=True,
                )
                return

            if game is None:
                await response_send_message(
                    ctx,
                    content=format_user_error_message("no_active_lobby"),
                    ephemeral=True,
                )
                return

            if game not in GAME_TYPES:
                await response_send_message(
                    ctx,
                    content=format_user_error_message("game_invalid", game=game),
                    ephemeral=True,
                )
                return

            # Start a new matchmaking lobby
            from cogs.games import begin_game

            await begin_game(ctx, game)

            # Need to wait a bit or re-fetch to get the new matchmaker
            # Actually, handle the rest of it after begin_game finishes and we find the matchmaker
            mm_by_user = matchmaking_by_user_id()
            if ctx.user.id not in mm_by_user:
                # It might take a moment or begin_game failed
                return

        matchmaker: MatchmakingInterface = mm_by_user[ctx.user.id]
        from cogs.games import add_matchmaking_bot

        if matchmaker.private and matchmaker.creator.id != ctx.user.id:
            await response_send_message(
                ctx,
                content=format_user_error_message("invite_not_creator_private"),
                ephemeral=True,
            )
            f_log.debug(f"/invite rejected: not creator. {contextify(ctx)}")
            return

        for difficulty in requested_bots:
            await add_matchmaking_bot(ctx, difficulty)

        game_type = matchmaker.game.name
        failed_invites = {}
        for invited_user in invited_users:
            if invited_user not in matchmaker.message.guild.members:
                failed_invites[invited_user] = get(
                    "matchmaking.invite_failed_not_in_server"
                )
                continue
            if invited_user.id in [p.id for p in matchmaker.queued_players]:
                failed_invites[invited_user] = get(
                    "matchmaking.invite_failed_already_queued"
                )
                continue
            if user_in_active_game(invited_user.id):
                failed_invites[invited_user] = get("matchmaking.invite_failed_in_game")
                continue
            if invited_user.bot:
                failed_invites[invited_user] = get("matchmaking.invite_failed_bot")
                continue

            # Invitation
            container = InviteContainer(
                inviter=ctx.user,
                game_type=game_type,
                guild_name=matchmaker.message.guild.name,
            )

            await invited_user.send(
                view=InviteView(
                    join_button_id=BUTTON_PREFIX_INVITE + str(matchmaker.message.id),
                    game_link=matchmaker.message.jump_url,
                    summary_text=container_to_markdown(container),
                ),
            )

        if not invited_users:
            return

        if not len(failed_invites):
            f_log.debug(
                f"/invite success: {len(invited_users)} succeeded, 0 failed. {contextify(ctx)}"
            )
            if ctx.response.is_done():
                await followup_send(ctx, get("success.invites_sent"), ephemeral=True)
            else:
                await response_send_message(
                    ctx, get("success.invites_sent"), ephemeral=True
                )
            return
        elif len(failed_invites) == len(invited_users):
            message = get("matchmaking.invites_failed_all")
        else:
            message = get("matchmaking.invites_failed_partial")
        f_log.debug(
            f"/invite partial or no success: {len(invited_users) - len(failed_invites)} succeeded,"
            f" {len(failed_invites)} failed. {contextify(ctx)}"
        )
        final = message + "\n"
        for fail in failed_invites:
            final += f"{fail.mention} - {failed_invites[fail]}\n"

        if ctx.response.is_done():
            await followup_send(ctx, final, ephemeral=True)
        else:
            await response_send_message(ctx, final, ephemeral=True)

    @command_root.command(name="kick", description=get("commands.kick.description"))
    @app_commands.check(interaction_check)
    @app_commands.describe(
        user=get("commands.kick.param_user"),
        reason=get("commands.kick.param_reason"),
    )
    async def command_kick(
        self, ctx: discord.Interaction, user: discord.User, reason: str = None
    ):
        f_log = log.getChild("command.kick")
        f_log.debug(
            "/kick called by user=%s target=%s reason=%r",
            ctx.user.id if ctx.user else None,
            getattr(user, "id", None),
            reason,
        )
        mm_by_user = matchmaking_by_user_id()

        if ctx.user.id not in mm_by_user:
            await response_send_message(
                ctx,
                content=format_user_error_message("kick_no_lobby"),
                ephemeral=True,
            )
            return
        matchmaker: MatchmakingInterface = mm_by_user[ctx.user.id]
        if matchmaker.creator.id != ctx.user.id:
            await response_send_message(
                ctx,
                content=format_user_error_message("kick_not_creator"),
                ephemeral=True,
            )
            return

        return_value = await matchmaker.kick(user, reason)
        f_log.info(
            "Kick executed by %s on %s result=%r",
            ctx.user.id if ctx.user else None,
            getattr(user, "id", None),
            return_value,
        )
        await response_send_message(ctx, return_value, ephemeral=True)

    @command_root.command(name="ban", description=get("commands.ban.description"))
    @app_commands.check(interaction_check)
    @app_commands.describe(
        user=get("commands.ban.param_user"),
        reason=get("commands.ban.param_reason"),
    )
    async def command_ban(
        self, ctx: discord.Interaction, user: discord.User, reason: str = None
    ):
        f_log = log.getChild("command.ban")
        f_log.debug(
            "/ban called by user=%s target=%s reason=%r",
            ctx.user.id if ctx.user else None,
            getattr(user, "id", None),
            reason,
        )
        mm_by_user = matchmaking_by_user_id()

        if ctx.user.id not in mm_by_user:
            await response_send_message(
                ctx,
                content=format_user_error_message("ban_no_lobby"),
                ephemeral=True,
            )
            return
        matchmaker: MatchmakingInterface = mm_by_user[ctx.user.id]
        if matchmaker.creator.id != ctx.user.id:
            await response_send_message(
                ctx,
                content=format_user_error_message("ban_not_creator"),
                ephemeral=True,
            )
            return

        return_value = await matchmaker.ban(user, reason)
        f_log.info(
            "Ban executed by %s on %s result=%r",
            ctx.user.id if ctx.user else None,
            getattr(user, "id", None),
            return_value,
        )
        await response_send_message(ctx, return_value, ephemeral=True)

    @command_root.command(name="stats", description=get("commands.stats.description"))
    @app_commands.check(interaction_check)
    async def command_stats(self, ctx: discord.Interaction):
        f_log = log.getChild("command.stats")
        f_log.debug(f"/stats called: {contextify(ctx)}")

        server_count = len(self.bot.guilds)
        member_count = len(set(self.bot.get_all_members()))

        shard_id = ctx.guild.shard_id if ctx.guild else 0
        shard_ping = self.bot.latency
        shard_servers = len(
            [guild for guild in self.bot.guilds if guild.shard_id == shard_id]
        )

        container = CustomContainer(
            title=f'{get("embeds.stats.title")} {get_emoji_string("pointing")}',
            description=fmt("embeds.stats.description", managed_by=MANAGED_BY),
            color=INFO_COLOR,
        )

        container.add_field(
            name="Bot",
            value=f"v{VERSION} · discord.py {discord.__version__}",
        )
        container.add_field(
            name="Servers",
            value=f"{server_count} servers · {len(GAME_TYPES)} games · {len(self.bot.effective_owner_ids)} owners",
        )
        container.add_field(
            name="Shard",
            value=f"#{shard_id} · {round(shard_ping * 100, 2)}ms · {shard_servers} servers",
        )
        container.add_field(
            name="System",
            value=f"{ramcheck.get_ram_usage_mb()} RAM",
        )
        container.add_field(
            name="Activity",
            value=f"{member_count} members · {len(IN_MATCHMAKING)} queuing · {len(IN_GAME)} in game",
            inline=False,
        )

        await response_send_message(ctx, **container_send_kwargs(container))

    @command_root.command(name="about", description=get("commands.about.description"))
    @app_commands.check(interaction_check)
    async def command_about(self, ctx: discord.Interaction):
        f_log = log.getChild("command.about")
        libraries = [
            "discord.py",
            "svg.py",
            "ruamel.yaml",
            "cairosvg",
            "trueskill",
            "mpmath",
            "emoji",
            "pillow",
            "psycopg",
            "psutil",
            "matplotlib",
        ]
        f_log.debug(f"/about called: {contextify(ctx)}")

        container = CustomContainer(title=get("embeds.about.title"), color=INFO_COLOR)
        container.add_field(
            name="Credits",
            value=(
                "Bot by [@quantumbagel](https://github.com/quantumbagel) · "
                "Art by [@soldship](https://github.com/quantumsoldship) · "
                "Inspired by [LoRiggio](https://github.com/Pixelz22/LoRiggioDev)"
            ),
            inline=False,
        )
        container.add_field(
            name="Source",
            value="[GitHub](https://github.com/PlayCord/bot)",
            inline=False,
        )
        container.add_field(
            name="Libraries",
            value=" · ".join(
                [f"[{lib}](https://pypi.org/project/{lib})" for lib in libraries]
            ),
            inline=False,
        )
        container.add_field(
            name="Dev Timeline",
            value="October 2024 - March 2025 · March 2026 - Present",
        )
        container.set_footer(
            text=get("embeds.about.footer"), icon_url=get("brand.footer_icon")
        )

        await response_send_message(ctx, **container_send_kwargs(container))

    @command_root.command(name="help", description=get("commands.help.description"))
    @app_commands.check(interaction_check)
    @app_commands.describe(topic=get("commands.help.param_topic"))
    @app_commands.choices(
        topic=[
            Choice(
                name=get("commands.help.choice_getting_started"),
                value="getting_started",
            ),
            Choice(name=get("commands.help.choice_commands"), value="commands"),
            Choice(name=get("commands.help.choice_games"), value="games"),
            Choice(name=get("help.buttons.game_tutorials"), value="tutorials"),
            Choice(name=get("help.buttons.faq"), value="faq"),
        ]
    )
    async def command_help(self, ctx: discord.Interaction, topic: str = None):
        f_log = log.getChild("command.help")
        f_log.debug(f"/help called with topic={topic}: {contextify(ctx)}")

        # Determine which container to show based on topic
        if topic == "getting_started":
            container = HelpGettingStartedContainer()
            section = "getting_started"
        elif topic == "commands":
            container = HelpCommandsContainer()
            section = "commands"
        elif topic == "tutorials":
            container = HelpTutorialsContainer()
            section = "tutorials"
        elif topic == "faq":
            container = HelpFaqContainer()
            section = "faq"
        elif topic == "games":
            container = await self._build_help_games_container()
            section = "games"
        else:
            container = HelpMainContainer()
            section = "main"

        view = HelpView(
            user_id=ctx.user.id,
            current_section=section,
            body_text=container_to_markdown(container),
        )
        await response_send_message(ctx, view=view)

    async def _build_help_games_container(self):
        """Build a quick games overview container for help menu."""
        container = CustomContainer(
            title=get("help.games_overview.title"),
            description=get("help.games_overview.description"),
            color=INFO_COLOR,
        )

        games_text = []
        for game_id in list(GAME_TYPES)[:HELP_GAMES_PREVIEW_COUNT]:
            game_name = _GAME_METADATA[game_id]["name"]
            games_text.append(
                fmt(
                    "help.games_overview.game_entry",
                    game_name=game_name,
                    game_id=game_id,
                )
            )

        if len(GAME_TYPES) > HELP_GAMES_PREVIEW_COUNT:
            games_text.append(
                fmt(
                    "help.games_overview.more_games",
                    count=len(GAME_TYPES) - HELP_GAMES_PREVIEW_COUNT,
                ),
            )

        container.add_field(
            name=get("help.games_overview.field_games"),
            value="\n".join(games_text),
            inline=False,
        )

        container.add_field(
            name=get("help.games_overview.field_tip"),
            value=get("help.games_overview.tip_value"),
            inline=False,
        )

        return container

    @command_root.command(
        name="leaderboard", description=get("commands.leaderboard.description")
    )
    @app_commands.check(interaction_check)
    @app_commands.describe(
        game=get("commands.leaderboard.param_game"),
        scope=get("commands.leaderboard.param_scope"),
        page=get("commands.leaderboard.param_page"),
    )
    @app_commands.choices(
        scope=[
            Choice(name=get("commands.leaderboard.choice_server"), value="server"),
            Choice(name=get("commands.leaderboard.choice_global"), value="global"),
        ]
    )
    @app_commands.autocomplete(game=autocomplete_game_id)
    async def command_leaderboard(
        self, ctx: discord.Interaction, game: str, scope: str = "server", page: int = 1
    ):
        f_log = log.getChild("command.leaderboard")
        f_log.debug(
            f"/leaderboard called for game={game}, scope={scope}, page={page}: {contextify(ctx)}"
        )

        if game not in GAME_TYPES:
            await response_send_message(
                ctx,
                content=format_user_error_message("game_invalid", game=game),
                ephemeral=True,
            )
            return

        # Defer response for database query (shows "thinking...")
        await ctx.response.defer()

        game_name = _GAME_METADATA[game]["name"]
        game_db = db.database.get_game(game)
        if not game_db:
            # errors are now single-line under [errors]; use format_user_error_message to preserve formatting
            await followup_send(
                ctx,
                content=format_user_error_message("game_not_registered"),
                ephemeral=True,
            )
            return

        if page < 1:
            page = 1

        limit = LEADERBOARD_PAGE_SIZE

        container, has_data, is_last_page = await self._build_leaderboard_container(
            game, game_name, game_db.game_id, scope, ctx.guild, page, limit
        )

        # If no data on this page and page > 1, go back to page 1
        if not has_data and page > 1:
            page = 1
            container, has_data, is_last_page = await self._build_leaderboard_container(
                game, game_name, game_db.game_id, scope, ctx.guild, page, limit
            )

        max_pages = page if is_last_page else page + 1
        container.set_footer(
            text=fmt("embeds.leaderboard.footer", page=page, max=max_pages)
        )

        view = PaginationView(
            guild_id=ctx.guild.id if ctx.guild else 0,
            user_id=ctx.user.id,
            current_page=page,
            max_pages=max_pages,
            body_text=container_to_markdown(container),
            callback_handler=lambda interaction, new_page: self._leaderboard_page_callback(
                interaction, game, game_name, game_db.game_id, scope, new_page, limit
            ),
        )
        await followup_send(ctx, view=view)

    async def _build_leaderboard_container(
        self,
        game: str,
        game_name: str,
        game_id: int,
        scope: str,
        guild,
        page: int,
        limit: int,
    ):
        """Build leaderboard container for a specific page. Returns (container, has_data, is_last_page)."""
        offset = (page - 1) * limit
        if scope == "global":
            # Fetch one extra item to check if there are more pages
            leaderboard_data = db.database.get_global_leaderboard(
                game_id,
                limit=limit + 1,
                offset=offset,
                min_matches=1,
            )
            scope_text = get("leaderboard.scope_global")
        else:
            member_ids: list[int] = []
            if guild is not None:
                await guild.chunk()
                member_ids = [m.id for m in guild.members]
            leaderboard_data = db.database.get_leaderboard(
                member_ids,
                game_id,
                limit=limit + 1,
                offset=offset,
                min_matches=1,
            )
            gname = guild.name if guild is not None else "—"
            scope_text = fmt("leaderboard.scope_server", guild_name=gname)

        title_key = (
            "embeds.leaderboard.title_global"
            if scope == "global"
            else "embeds.leaderboard.title_server"
        )
        container = CustomContainer(
            title=fmt(title_key, game_name=game_name), color=INFO_COLOR
        )
        container.description = scope_text

        has_data = bool(leaderboard_data)
        # If we got more than limit items, there are more pages
        is_last_page = len(leaderboard_data) <= limit

        # Only use the first 'limit' items for display
        display_data = leaderboard_data[:limit]

        if not display_data:
            container.add_field(
                name=get("leaderboard.no_data_name"),
                value=(
                    get("embeds.leaderboard.no_players")
                    if page == 1
                    else get("embeds.leaderboard.no_more_players")
                ),
                inline=False,
            )
        else:
            rankings = []
            for i, entry in enumerate(display_data, start=offset + 1):
                user_id = entry["user_id"]
                conservative = entry.get("conservative_rating", entry.get("mu", 0))
                mu = entry.get("mu", 0)
                matches = entry.get("matches_played", 0)
                medal = (
                    get("format.rank_medal_1")
                    if i == 1
                    else (
                        get("format.rank_medal_2")
                        if i == 2
                        else (
                            get("format.rank_medal_3")
                            if i == 3
                            else fmt("format.rank_number", rank=i)
                        )
                    )
                )
                rankings.append(
                    fmt(
                        "embeds.leaderboard.ranking_format",
                        medal=medal,
                        user_id=user_id,
                        conservative=round(conservative),
                        mu=round(mu),
                        matches=matches,
                        games_word=plural("game", matches),
                    )
                )
            container.add_field(
                name=get("embeds.leaderboard.field_rankings"),
                value="\n".join(rankings),
                inline=False,
            )

        return container, has_data, is_last_page

    async def _leaderboard_page_callback(
        self,
        interaction: discord.Interaction,
        game: str,
        game_name: str,
        game_id: int,
        scope: str,
        new_page: int,
        limit: int,
    ):
        """Callback for leaderboard pagination buttons."""
        container, has_data, is_last_page = await self._build_leaderboard_container(
            game, game_name, game_id, scope, interaction.guild, new_page, limit
        )
        max_pages = new_page if is_last_page else new_page + 1
        container.set_footer(
            text=fmt("embeds.leaderboard.footer", page=new_page, max=max_pages)
        )
        view = PaginationView(
            guild_id=interaction.guild.id if interaction.guild else 0,
            user_id=interaction.user.id,
            current_page=new_page,
            max_pages=max_pages,  # Dynamic max based on data
            body_text=container_to_markdown(container),
            callback_handler=lambda inter, pg: self._leaderboard_page_callback(
                inter, game, game_name, game_id, scope, pg, limit
            ),
        )
        await interaction.edit_original_response(view=view)

    @command_root.command(
        name="catalog", description=get("commands.catalog.description")
    )
    @app_commands.check(interaction_check)
    @app_commands.describe(page=get("commands.catalog.param_page"))
    async def command_catalog(self, ctx: discord.Interaction, page: int = 1):
        f_log = log.getChild("command.catalog")
        f_log.debug(f"/catalog called with page={page}: {contextify(ctx)}")

        games_per_page = CATALOG_GAMES_PER_PAGE
        all_games = list(GAME_TYPES)
        total_pages = (len(all_games) + games_per_page - 1) // games_per_page

        if page < 1 or page > total_pages:
            page = 1

        container = self._build_catalog_container(
            page, total_pages, all_games, games_per_page
        )

        view = PaginationView(
            guild_id=ctx.guild.id if ctx.guild else 0,
            user_id=ctx.user.id,
            current_page=page,
            max_pages=total_pages,
            body_text=container_to_markdown(container),
            callback_handler=lambda interaction, new_page: self._catalog_page_callback(
                interaction, new_page, total_pages, all_games, games_per_page
            ),
        )
        await response_send_message(ctx, view=view)

    def _build_catalog_container(
        self, page: int, total_pages: int, all_games: list, games_per_page: int
    ) -> CustomContainer:
        """Build the catalog container for a specific page."""
        start_idx = (page - 1) * games_per_page
        page_games = all_games[start_idx : start_idx + games_per_page]

        container = CustomContainer(
            title=fmt("embeds.catalog.title", name=NAME), color=INFO_COLOR
        )
        container.description = fmt("embeds.catalog.description", count=len(GAME_TYPES))

        for game_id in page_games:
            meta = _GAME_METADATA[game_id]
            game_class = meta["class"]
            game_name = meta["name"]
            game_desc = meta["description"] or get("help.game_info.no_description")
            game_time = meta["time"] or get("help.game_info.unknown")
            game_difficulty = meta["difficulty"] or get("help.game_info.unknown")
            game_players = resolve_player_count(game_class)
            if game_players is None:
                game_players = get("help.game_info.unknown")
            game_emoji = get_game_emoji(game_id)
            if isinstance(game_players, list):
                player_text = fmt(
                    "help.game_info.players_range_format",
                    min=min(game_players),
                    max=max(game_players),
                )
            else:
                player_text = fmt("help.game_info.players_format", count=game_players)

            short_desc = f"{game_desc[:100]}{'...' if len(game_desc) > 100 else ''}"
            container.add_field(
                name=fmt(
                    "embeds.catalog.game_field_format",
                    emoji=game_emoji,
                    game_name=game_name,
                ),
                value=fmt(
                    "embeds.catalog.game_value_format",
                    description=short_desc,
                    time=game_time,
                    players=player_text,
                    difficulty=game_difficulty,
                    game_id=game_id,
                ),
                inline=False,
            )

        container.set_footer(
            text=fmt("embeds.catalog.footer", page=page, total=total_pages)
        )
        return container

    async def _catalog_page_callback(
        self,
        interaction: discord.Interaction,
        new_page: int,
        total_pages: int,
        all_games: list,
        games_per_page: int,
    ):
        """Callback for catalog pagination buttons."""
        container = self._build_catalog_container(
            new_page, total_pages, all_games, games_per_page
        )
        view = PaginationView(
            guild_id=interaction.guild.id if interaction.guild else 0,
            user_id=interaction.user.id,
            current_page=new_page,
            max_pages=total_pages,
            body_text=container_to_markdown(container),
            callback_handler=lambda inter, pg: self._catalog_page_callback(
                inter, pg, total_pages, all_games, games_per_page
            ),
        )
        await interaction.edit_original_response(view=view)

    @command_root.command(
        name="profile", description=get("commands.profile.description")
    )
    @app_commands.check(interaction_check)
    @app_commands.describe(user=get("commands.profile.param_user"))
    async def command_profile(
        self, ctx: discord.Interaction, user: discord.User = None
    ):
        f_log = log.getChild("command.profile")
        if user is None:
            user = ctx.user
        f_log.debug(f"/profile called for user={user.id}: {contextify(ctx)}")

        # Defer for database queries
        await ctx.response.defer()

        player = db.database.get_player(user, ctx.guild.id)
        if player is None:
            await followup_send(
                ctx,
                content=format_user_error_message(
                    "player_not_found", player_name=user.display_name
                ),
                ephemeral=True,
            )
            return

        container = CustomContainer(
            title=fmt("embeds.profile.title", username=user.display_name),
            color=INFO_COLOR,
        )
        container.set_thumbnail(url=user.display_avatar.url)

        game_stats = []
        for game_id in GAME_TYPES:
            game_name = _GAME_METADATA[game_id]["name"]
            rating_info = db.database.get_user_game_ratings(user.id, game_id)
            if rating_info and rating_info.get("matches_played", 0) > 0:
                mu = rating_info.get("mu", MU)
                matches = rating_info.get("matches_played", 0)

                # Check for global rank
                game_db = db.database.get_game(game_id)
                if game_db:
                    global_rank = db.database.get_user_global_rank(
                        user.id, game_db.game_id
                    )
                    if global_rank is not None and global_rank <= 100:
                        rank_badge = (
                            get("format.rank_badge_1")
                            if global_rank == 1
                            else (
                                get("format.rank_badge_top3")
                                if global_rank <= 3
                                else (
                                    get("format.rank_badge_top10")
                                    if global_rank <= 10
                                    else ""
                                )
                            )
                        )
                        game_stats.append(
                            fmt(
                                "embeds.profile.rating_format_ranked",
                                game_name=game_name,
                                rating=round(mu),
                                matches=matches,
                                games_word=plural("game", matches),
                                badge=rank_badge,
                                rank=global_rank,
                            )
                        )
                    else:
                        game_stats.append(
                            fmt(
                                "embeds.profile.rating_format",
                                game_name=game_name,
                                rating=round(mu),
                                matches=matches,
                                games_word=plural("game", matches),
                            )
                        )
                else:
                    game_stats.append(
                        fmt(
                            "embeds.profile.rating_format",
                            game_name=game_name,
                            rating=round(mu),
                            matches=matches,
                            games_word=plural("game", matches),
                        )
                    )

        if game_stats:
            container.add_field(
                name=get("embeds.profile.field_ratings"),
                value="\n".join(game_stats),
                inline=False,
            )
        else:
            container.add_field(
                name=get("embeds.profile.field_ratings"),
                value=get("embeds.profile.field_ratings_empty"),
                inline=False,
            )

        match_history = db.database.get_user_match_history(
            user.id, ctx.guild.id, limit=5
        )
        if match_history:
            history_lines = [
                fmt(
                    "embeds.profile.match_format",
                    game_name=m.get("game_name", get("help.game_info.unknown")),
                    ranking=(
                        _ordinal(m.get("final_ranking"))
                        if m.get("final_ranking")
                        else "-"
                    ),
                    player_count=m.get("player_count", "?"),
                    seat=m.get("player_number", "?"),
                    rated_status=(
                        get("history.rated")
                        if m.get("is_rated", True)
                        else get("history.casual")
                    ),
                    status=_history_status_label(m.get("status")),
                    delta=f"{'+' if m.get('mu_delta', 0) >= 0 else ''}{round(m.get('mu_delta', 0))}",
                )
                for m in match_history
            ]
            container.add_field(
                name=get("embeds.profile.field_recent_matches"),
                value="\n".join(history_lines),
                inline=False,
            )
        else:
            container.add_field(
                name=get("embeds.profile.field_recent_matches"),
                value=get("embeds.profile.field_recent_matches_empty"),
                inline=False,
            )

        total_matches = 0
        for game_id in GAME_TYPES:
            rating_info = db.database.get_user_game_ratings(user.id, game_id)
            if rating_info:
                total_matches += int(rating_info.get("matches_played", 0))
        container.add_field(
            name=get("embeds.profile.field_total_games"),
            value=f"{total_matches} {plural('game', total_matches)}",
            inline=True,
        )
        await followup_send(ctx, **container_send_kwargs(container))

    @command_root.command(
        name="history", description=get("commands.history.description")
    )
    @app_commands.check(interaction_check)
    @app_commands.describe(
        game=get("commands.history.param_game"),
        user=get("commands.history.param_user"),
        page=get("commands.history.param_page"),
        days=get("commands.history.param_days"),
    )
    @app_commands.autocomplete(game=autocomplete_game_id)
    async def command_history(
        self,
        ctx: discord.Interaction,
        game: str,
        user: discord.User = None,
        page: int = 1,
        days: int = 30,
    ):
        f_log = log.getChild("command.history")
        if user is None:
            user = ctx.user
        if page < 1:
            page = 1
        days = max(1, min(days, 365))

        f_log.debug(
            f"/history called for game={game}, user={user.id}, page={page}, days={days}: {contextify(ctx)}"
        )

        resolved_game, suggestion = _resolve_game_id_input(game)
        if resolved_game is None:
            message = fmt("history.unknown_game", game=game)
            if suggestion:
                message = f"{message}\n\nDid you mean `{suggestion}`?"
            await response_send_message(
                ctx,
                message,
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        game = resolved_game

        game_db = db.database.get_game(game)
        if not game_db:
            await response_send_message(
                ctx,
                content=format_user_error_message("game_not_registered"),
                ephemeral=True,
            )
            return

        game_name = _GAME_METADATA[game]["name"]

        container, chart_file, has_data, is_last_page = self._build_history_container(
            user, game_name, game_db.game_id, ctx.guild.id, page, days, f_log
        )

        max_pages = page if is_last_page else page + 1
        container.set_footer(
            text=fmt("pagination.page_footer", page=page, max=max_pages)
        )
        view = PaginationView(
            guild_id=ctx.guild.id if ctx.guild else 0,
            user_id=ctx.user.id,
            current_page=page,
            max_pages=max_pages,
            body_text=container_to_markdown(container),
            callback_handler=lambda interaction, new_page: self._history_page_callback(
                interaction, user, game_name, game_db.game_id, new_page, days, f_log
            ),
        )
        if chart_file:
            await response_send_message(ctx, view=view, file=chart_file)
        else:
            await response_send_message(ctx, view=view)

    def _build_history_container(
        self,
        user,
        game_name: str,
        game_id: int,
        guild_id: int,
        page: int,
        days: int,
        f_log,
    ):
        """Build history container for a specific page. Returns (container, chart_file, has_data, is_last_page)."""
        limit = HISTORY_PAGE_SIZE
        offset = (page - 1) * limit

        # Fetch one extra item to check if there are more pages
        match_history = db.database.get_user_match_history(
            user.id,
            guild_id,
            game_id=game_id,
            limit=limit + 1,
            offset=offset,
        )
        rating_history = db.database.get_rating_history(
            user.id, guild_id, game_id, days=days
        )

        container = CustomContainer(
            title=fmt("history.embed_title", user=user.display_name, game=game_name),
            color=INFO_COLOR,
        )
        container.set_thumbnail(url=user.display_avatar.url)

        has_data = bool(match_history)
        # If we got more than limit items, there are more pages
        is_last_page = len(match_history) <= limit

        # Only use the first 'limit' items for display
        display_history = match_history[:limit]

        if display_history:
            lines = []
            for row in display_history:
                rank_text = _ordinal(row.get("final_ranking"))
                delta = row.get("mu_delta", 0)
                meta = row.get("metadata") or {}
                if not isinstance(meta, dict):
                    meta = {}
                summ = None
                by_player = meta.get("outcome_summaries")
                if isinstance(by_player, dict):
                    summ = by_player.get(str(user.id))
                if summ is None:
                    summ = meta.get("outcome_summary")
                summ_txt = ""
                if summ:
                    s = str(summ)
                    if len(s) > 72:
                        s = s[:69] + "..."
                    summ_txt = f" — {s}"
                mid = row.get("match_code") or row.get("match_id", "?")
                gkey = row.get("game_key") or "?"
                lines.append(
                    f"`{mid}` `{gkey}` · {rank_text}/{row.get('player_count', '?')} | "
                    f"{fmt('history.seat', seat=row.get('player_number', '?'))}"
                    f" | {get('history.rated') if row.get('is_rated', True) else get('history.casual')}"
                    f" | {_history_status_label(row.get('status'))}"
                    f" | {'+' if delta >= 0 else ''}{round(delta)}{summ_txt}"
                )
            container.add_field(
                name=get("history.recent_matches"), value="\n".join(lines), inline=False
            )
        else:
            container.add_field(
                name=get("history.recent_matches"),
                value=(
                    get("history.no_completed") if page == 1 else get("history.no_more")
                ),
                inline=False,
            )

        # Generate matplotlib chart if rating history exists (only on first page for performance)
        chart_file = None
        if rating_history and page == 1:
            ascending = list(reversed(rating_history))
            points = [ascending[0].get("mu_before", MU)] + [
                row.get("mu_after", MU) for row in ascending
            ]
            timestamps = [
                datetime.fromisoformat(str(ascending[0].get("created_at")))
            ] + [
                datetime.fromisoformat(str(row.get("created_at"))) for row in ascending
            ]

            rating_data = list(zip(timestamps, points))

            try:
                chart_buffer = generate_elo_chart(
                    rating_data,
                    title=fmt(
                        "history.chart_title", user=user.display_name, game=game_name
                    ),
                    figsize=(10, 6),
                    dpi=100,
                )
                chart_file = discord.File(chart_buffer, filename="rating_chart.png")
                container.set_image(url="attachment://rating_chart.png")

                delta_total = points[-1] - points[0]
                container.add_field(
                    name=fmt("history.rating_trend_name", days=days),
                    value=(
                        f"{get('history.start')}: {round(points[0])} → {get('history.end')}: {round(points[-1])} "
                        f"({'+' if delta_total >= 0 else ''}{round(delta_total)})"
                    ),
                    inline=False,
                )
            except Exception as e:
                f_log.error(f"Failed to generate chart: {e}")
                delta_total = points[-1] - points[0]
                container.add_field(
                    name=fmt("history.rating_trend_name", days=days),
                    value=(
                        f"{get('history.start')}: {round(points[0])} → {get('history.end')}: {round(points[-1])} "
                        f"({'+' if delta_total >= 0 else ''}{round(delta_total)})"
                    ),
                    inline=False,
                )
        elif page == 1:
            container.add_field(
                name=fmt("history.rating_trend_name", days=days),
                value=get("history.no_rating_period"),
                inline=False,
            )

        return container, chart_file, has_data, is_last_page

    async def _history_page_callback(
        self,
        interaction: discord.Interaction,
        user,
        game_name: str,
        game_id: int,
        new_page: int,
        days: int,
        f_log,
    ):
        """Callback for history pagination buttons."""
        container, chart_file, has_data, is_last_page = self._build_history_container(
            user, game_name, game_id, interaction.guild.id, new_page, days, f_log
        )
        max_pages = new_page if is_last_page else new_page + 1
        container.set_footer(
            text=fmt("pagination.page_footer", page=new_page, max=max_pages)
        )
        view = PaginationView(
            guild_id=interaction.guild.id if interaction.guild else 0,
            user_id=interaction.user.id,
            current_page=new_page,
            max_pages=max_pages,  # Dynamic max based on data
            body_text=container_to_markdown(container),
            callback_handler=lambda inter, pg: self._history_page_callback(
                inter, user, game_name, game_id, pg, days, f_log
            ),
        )
        # Chart file only on page 1, so we won't have it on other pages
        await interaction.edit_original_response(view=view)

    def _replay_game_label(self, game_id: int) -> str:
        g = db.database.get_game_by_id(game_id)
        if g is None:
            return str(game_id)
        return getattr(g, "display_name", None) or getattr(g, "game_name", str(game_id))

    def _build_replay_container(
        self,
        match_id: int,
        game_label: str,
        pages: list[str],
        page_1based: int,
        global_summary: str | None = None,
        *,
        replay_display: str | None = None,
    ) -> CustomContainer:
        total = max(1, len(pages))
        p = max(1, min(page_1based, total))
        body = pages[p - 1] if pages else ""
        code = f"```{body}```" if body.strip() else get("commands.replay.empty_page")
        head = ""
        if global_summary and str(global_summary).strip():
            head = f"{str(global_summary).strip()}\n\n"
        desc = (head + code)[:TEXT_DISPLAY_MAX]
        disp = replay_display if replay_display is not None else str(match_id)
        container = CustomContainer(
            title=fmt("commands.replay.title", id=disp, game=game_label),
            description=desc,
        )
        container.set_footer(text=fmt("pagination.page_footer", page=p, max=total))
        return container

    async def _replay_page_callback(
        self,
        interaction: discord.Interaction,
        new_page: int,
        pages: list[str],
        match_id: int,
        game_label: str,
        global_summary: str | None,
        replay_display: str,
    ):
        container = self._build_replay_container(
            match_id,
            game_label,
            pages,
            new_page,
            global_summary=global_summary,
            replay_display=replay_display,
        )
        view = PaginationView(
            guild_id=interaction.guild.id if interaction.guild else 0,
            user_id=interaction.user.id,
            current_page=new_page,
            max_pages=len(pages),
            body_text=container_to_markdown(container),
            callback_handler=lambda inter, np: self._replay_page_callback(
                inter, np, pages, match_id, game_label, global_summary, replay_display
            ),
        )
        await interaction.edit_original_response(view=view)

    @command_root.command(name="replay", description=get("commands.replay.description"))
    @app_commands.describe(match_ref=get("commands.replay.param_match_ref"))
    @app_commands.guild_only()
    @app_commands.check(interaction_check)
    async def command_replay(
        self, ctx: discord.Interaction, match_ref: app_commands.Range[str, 1, 32]
    ):
        await ctx.response.defer(ephemeral=True)
        if ctx.guild is None:
            await followup_send(
                ctx, content=get("commands.set_channel.guild_only"), ephemeral=True
            )
            return
        raw = (match_ref or "").strip()
        match = resolve_match_for_replay(raw, ctx.guild.id)
        if match is None:
            await followup_send(
                ctx,
                content=format_user_error_message("replay_not_found"),
                ephemeral=True,
            )
            return
        match_id = match.match_id
        replay_display = (match.match_code or "").strip() or str(match_id)
        events = db.database.get_replay_events(match_id)
        if not events:
            await followup_send(
                ctx,
                content=fmt("commands.replay.no_data", match_display=replay_display),
                ephemeral=True,
            )
            return
        lines = [format_replay_event_line(e) for e in events]
        pages = chunk_replay_lines(lines)
        game_label = self._replay_game_label(match.game_id)
        meta = match.metadata or {}
        replay_global = None
        if isinstance(meta, dict):
            replay_global = meta.get("outcome_global_summary")
            if replay_global is not None:
                replay_global = str(replay_global).strip() or None
        container = self._build_replay_container(
            match_id,
            game_label,
            pages,
            1,
            global_summary=replay_global,
            replay_display=replay_display,
        )
        view = PaginationView(
            guild_id=ctx.guild.id,
            user_id=ctx.user.id,
            current_page=1,
            max_pages=len(pages),
            body_text=container_to_markdown(container),
            callback_handler=lambda inter, np: self._replay_page_callback(
                inter, np, pages, match_id, game_label, replay_global, replay_display
            ),
        )
        await followup_send(ctx, view=view, ephemeral=True)

    @command_replay.autocomplete("match_ref")
    async def replay_autocomplete(
        self, ctx: discord.Interaction, current: str
    ) -> list[Choice[str]]:
        if ctx.guild is None:
            return []

        needle = (current or "").strip().lower()
        rows = db.database.get_user_match_history(
            user_id=ctx.user.id,
            guild_id=ctx.guild.id,
            limit=25,
        )

        choices: list[Choice[str]] = []
        seen: set[str] = set()
        for row in rows:
            code = str(row.get("match_code") or row.get("match_id") or "").strip()
            if not code or code in seen:
                continue

            game = str(row.get("game_name") or row.get("game_key") or "?").strip()
            haystack = f"{game} {code}".lower()
            if needle and needle not in haystack:
                continue

            seen.add(code)
            choices.append(Choice(name=f"{game} - {code}"[:100], value=code))
            if len(choices) >= 25:
                break
        return choices

    @command_root.command(
        name="feedback", description=get("commands.feedback.description")
    )
    @app_commands.describe(message=get("commands.feedback.param_message"))
    @app_commands.check(interaction_check)
    async def command_feedback(
        self, ctx: discord.Interaction, message: app_commands.Range[str, 1, 500]
    ):
        text = (message or "").strip()
        if not text:
            await response_send_message(
                ctx,
                get("commands.feedback.empty"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        owner_ids = set(ctx.client.effective_owner_ids)

        guild_name = ctx.guild.name if ctx.guild else "Direct Message"
        delivered = 0
        body = (
            f"## Feedback\n"
            f"From: {ctx.user} (`{ctx.user.id}`)\n"
            f"Guild: {guild_name}\n"
            f"Channel: {getattr(ctx.channel, 'mention', 'Unknown')}\n\n"
            f"{text}"
        )
        for target_id in owner_ids:
            try:
                owner = ctx.client.get_user(target_id) or await ctx.client.fetch_user(
                    target_id
                )
                await owner.send(body)
                delivered += 1
            except discord.HTTPException:
                continue

        if delivered == 0:
            await response_send_message(
                ctx,
                get("commands.feedback.delivery_failed"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        await response_send_message(
            ctx,
            get("commands.feedback.thanks"),
            ephemeral=True,
            delete_after=EPHEMERAL_DELETE_AFTER,
        )

    @command_root.command(name="forfeit", description=get("forfeit.description"))
    @app_commands.guild_only()
    @app_commands.check(interaction_check)
    async def command_forfeit(self, ctx: discord.Interaction):
        if ctx.channel.type != discord.ChannelType.private_thread:
            await response_send_message(
                ctx,
                get("forfeit.wrong_channel"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        game = CURRENT_GAMES.get(ctx.channel.id)
        if game is None:
            await response_send_message(
                ctx,
                get("forfeit.not_active"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        if ctx.user.id not in {p.id for p in game.players}:
            await response_send_message(
                ctx,
                get("forfeit.not_in_game"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        await ctx.response.defer(ephemeral=True)
        result = await game.forfeit_player(ctx.user.id)
        await followup_send(
            ctx, result, ephemeral=True, delete_after=EPHEMERAL_DELETE_AFTER
        )

    @command_root.command(
        name="settings", description=get("commands.settings.description")
    )
    @app_commands.check(interaction_check)
    @app_commands.describe(
        rated=get("commands.settings.param_rated"),
        private=get("commands.settings.param_private"),
    )
    async def command_settings(
        self, ctx: discord.Interaction, rated: bool = None, private: bool = None
    ):
        f_log = log.getChild("command.settings")
        f_log.debug(
            f"/settings called: rated={rated}, private={private} {contextify(ctx)}"
        )

        mm_by_user = matchmaking_by_user_id()
        if ctx.user.id not in mm_by_user:
            await response_send_message(
                ctx, get("settings.not_in_matchmaking"), ephemeral=True
            )
            return

        matchmaker: MatchmakingInterface = mm_by_user[ctx.user.id]
        if matchmaker.creator.id != ctx.user.id:
            await response_send_message(
                ctx, get("settings.only_creator"), ephemeral=True
            )
            return

        changes = []
        if rated is not None and rated != matchmaker.rated:
            if rated and getattr(matchmaker, "has_bots", False):
                await response_send_message(
                    ctx, get("settings.rated_blocked_bots"), ephemeral=True
                )
                return
            matchmaker.rated = rated
            changes.append(
                fmt(
                    "settings.changed_rated",
                    value=get("settings.yes") if rated else get("settings.no"),
                )
            )
        if private is not None and private != matchmaker.private:
            matchmaker.private = private
            changes.append(
                fmt(
                    "settings.changed_private",
                    value=get("settings.yes") if private else get("settings.no"),
                )
            )

        if changes:
            await matchmaker.update_embed()
            await response_send_message(
                ctx, get("settings.updated") + "\n" + "\n".join(changes), ephemeral=True
            )
        else:
            await response_send_message(ctx, get("settings.no_changes"), ephemeral=True)

    @command_root.command(
        name="set_channel", description=get("commands.set_channel.description")
    )
    @app_commands.check(interaction_check)
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel=get("commands.set_channel.param_channel"))
    async def command_set_channel(
        self,
        ctx: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ):
        if ctx.guild is None:
            await response_send_message(
                ctx, get("commands.set_channel.guild_only"), ephemeral=True
            )
            return
        await ctx.response.defer(ephemeral=True)
        if channel is None:
            db.database.merge_guild_settings(
                ctx.guild.id, {"playcord_channel_id": None}
            )
            await followup_send(
                ctx, content=get("commands.set_channel.cleared"), ephemeral=True
            )
            return
        db.database.merge_guild_settings(
            ctx.guild.id, {"playcord_channel_id": channel.id}
        )
        await followup_send(
            ctx,
            content=fmt("commands.set_channel.saved", channel=channel.mention),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))
