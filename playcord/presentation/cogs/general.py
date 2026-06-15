import importlib
from difflib import get_close_matches
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from playcord.api import ReplayableGame, RoleFlow, RoleMode
from playcord.api.plugin import resolve_player_count
from playcord.application.services import replay_viewer
from playcord.infrastructure import system_metrics as ramcheck
from playcord.infrastructure.constants import (
    CATALOG_GAMES_PER_PAGE,
    EPHEMERAL_DELETE_AFTER,
    GAME_TYPES,
    HISTORY_PAGE_SIZE,
    INFO_COLOR,
    LOGGING_ROOT,
    MANAGED_BY,
    NAME,
    VERSION,
)
from playcord.infrastructure.db_thread import run_in_thread
from playcord.infrastructure.locale import fmt, get
from playcord.infrastructure.logging import get_logger
from playcord.infrastructure.state.matchmaking_registry import matchmaking_by_user_id
from playcord.presentation.interactions.contextify import contextify
from playcord.presentation.interactions.helpers import (
    discord_user_db_label,
    followup_send,
    format_user_error_message,
    interaction_check,
    response_send_message,
    send_ephemeral_transient_text,
    send_format_user_error,
)
from playcord.presentation.ui.containers import (
    TEXT_DISPLAY_MAX,
    CustomContainer,
    container_send_kwargs,
    container_to_markdown,
)
from playcord.presentation.ui.emojis import get_emoji_string, get_game_emoji
from playcord.presentation.ui.formatting import (
    chunk_replay_lines,
    format_replay_event_line,
)
from playcord.presentation.ui.layout_discord import (
    PaginationView,
)
from playcord.presentation.ui.replay_views import ReplayViewerView

if TYPE_CHECKING:
    from playcord.presentation.interactions.matchmaking_lobby import (
        MatchmakingInterface,
    )

log = get_logger()

_GAME_METADATA: dict[str, dict] = {}


def _load_game_metadata() -> None:
    """Populate game class metadata once at import (avoids importlib per autocomplete keystroke)."""
    global _GAME_METADATA
    _GAME_METADATA = {}
    for gid, (mod_name, cls_name) in GAME_TYPES.items():
        game_class = getattr(importlib.import_module(mod_name), cls_name)
        metadata = game_class.metadata
        role_flow = getattr(metadata, "role_flow", RoleFlow.none)
        role_mode = getattr(metadata, "role_mode", RoleMode.none)
        supports_role_selection = (
            role_flow
            in (
                RoleFlow.selectable,
                RoleFlow.selectable_random,
            )
            or role_mode == RoleMode.chosen
        )
        _GAME_METADATA[gid] = {
            "class": game_class,
            "name": getattr(metadata, "name", gid),
            "summary": getattr(metadata, "summary", None),
            "description": getattr(metadata, "description", ""),
            "time": getattr(metadata, "time", None),
            "difficulty": getattr(metadata, "difficulty", None),
            "supports_role_selection": supports_role_selection,
            "supports_replays": issubclass(game_class, ReplayableGame),
            "supports_bots": bool(getattr(metadata, "bots", None)),
            "supports_lobby_options": bool(
                getattr(metadata, "customizable_options", ())
            ),
        }


_load_game_metadata()


def _catalog_bool_label(supported: bool) -> str:
    return get(
        "embeds.catalog.feature_yes" if supported else "embeds.catalog.feature_no"
    )


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


def _match_summary_for_user(
    metadata: object,
    user_id: int,
    *,
    max_len: int = 72,
) -> str | None:
    if not isinstance(metadata, dict):
        return None

    summary = None
    by_player = metadata.get("outcome_summaries")
    if isinstance(by_player, dict):
        summary = by_player.get(str(user_id))
    if summary is None:
        summary = metadata.get("outcome_global_summary") or metadata.get(
            "outcome_summary",
        )
    if summary is None:
        return None

    text = str(summary).strip()
    if not text:
        return None
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


def _fallback_match_outcome_label(match_row: dict[str, Any]) -> str:
    metadata = match_row.get("metadata")
    if isinstance(metadata, dict):
        final_state = metadata.get("final_state")
        if isinstance(final_state, dict):
            outcome = str(final_state.get("outcome", "")).strip().lower()
            if outcome == "draw":
                return "Draw"
            if outcome == "winner":
                ranking = match_row.get("final_ranking")
                try:
                    return "Win" if int(ranking) == 1 else "Loss"
                except (TypeError, ValueError):
                    return "Win"
            if outcome in {"interrupted", "abandoned"}:
                return "Interrupted"
    status = str(match_row.get("status", "")).strip().lower()
    if status in {"interrupted", "abandoned"}:
        return "Interrupted"
    ranking = match_row.get("final_ranking")
    try:
        rank_val = int(ranking)
    except (TypeError, ValueError):
        return "Completed"
    return "Win" if rank_val == 1 else "Loss"


def _outcome_for_recent_match(match_row: dict[str, Any], user_id: int) -> str:
    summary = _match_summary_for_user(match_row.get("metadata"), user_id, max_len=56)
    if summary:
        return summary
    return _fallback_match_outcome_label(match_row)


def _ordinal(value: Any) -> str:
    if value is None:
        return "?"
    try:
        rank_val = int(value)
    except (TypeError, ValueError):
        return "?"
    if 10 <= rank_val % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(rank_val % 10, "th")
    return f"{rank_val}{suffix}"


def _profile_supports_compact_avatar() -> bool:
    # Current container rendering shows thumbnails as media cards (large visual block).
    # Only display avatars here when compact thumbnail rendering is available.
    return False


def resolve_match_for_replay(raw: str, guild_id: int, *, matches: Any) -> Any:
    """Resolve a match from an 8-char public code or numeric id (Discord thread snowflake)."""
    from playcord.core.generators import is_match_code_token

    s = (raw or "").strip().lower()
    if not s:
        return None
    if is_match_code_token(s):
        m = matches.get_by_code(s)
        if m is not None and m.guild_id == guild_id:
            return m
        if s.isdigit():
            m2 = matches.get(int(s))
            if m2 is not None and m2.guild_id == guild_id:
                return m2
        return None
    if s.isdigit():
        m = matches.get(int(s))
        if m is not None and m.guild_id == guild_id:
            return m
    return None


async def autocomplete_game_id(
    ctx: discord.Interaction,
    current: str,
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
    private=get("commands.settings.param_private"),
)
@app_commands.autocomplete(game=autocomplete_game_id)
@app_commands.guild_only()
@app_commands.check(interaction_check)
async def command_play(
    ctx: discord.Interaction,
    game: str,
    private: bool = False,
) -> None:
    f_log = log.getChild("command.play")
    f_log.debug(
        "/play called by user=%s game=%r private=%s",
        getattr(ctx.user, "id", None),
        game,
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

    from playcord.presentation.cogs.games import begin_game

    await begin_game(ctx, game_type, private=private)


class GeneralCog(commands.Cog):
    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot
        c = bot.container
        self._matches = c.matches_repository
        self._games = c.games_repository
        self._players = c.players_repository
        self._guilds = c.guilds_repository

    @property
    def _replay_source(self) -> replay_viewer.ReplayDataSource | None:
        container = getattr(self.bot, "container", None)
        if container is None:
            return None
        return replay_viewer.ReplayDataSource(
            matches_repository=container.matches_repository,
            games_repository=container.games_repository,
            players_repository=container.players_repository,
            replays_repository=container.replays_repository,
        )

    command_root = app_commands.Group(
        name=LOGGING_ROOT,
        description=get("commands.group.description"),
        guild_only=False,
    )

    @command_root.command(name="kick", description=get("commands.kick.description"))
    @app_commands.check(interaction_check)
    @app_commands.describe(
        user=get("commands.kick.param_user"),
        reason=get("commands.kick.param_reason"),
    )
    async def command_kick(
        self,
        ctx: discord.Interaction,
        user: discord.User,
        reason: str | None = None,
    ) -> None:
        f_log = log.getChild("command.kick")
        f_log.debug(
            "/kick called by user=%s target=%s reason=%r",
            ctx.user.id if ctx.user else None,
            getattr(user, "id", None),
            reason,
        )
        mm_by_user = matchmaking_by_user_id()

        if ctx.user.id not in mm_by_user:
            await send_format_user_error(ctx, "kick_no_lobby")
            return
        matchmaker: MatchmakingInterface = mm_by_user[ctx.user.id]
        if matchmaker.creator.id != ctx.user.id:
            await send_format_user_error(ctx, "kick_not_creator")
            return

        return_value = await matchmaker.kick(user, reason)
        f_log.info(
            "Kick executed by %s on %s result=%r",
            ctx.user.id if ctx.user else None,
            getattr(user, "id", None),
            return_value,
        )
        await send_ephemeral_transient_text(ctx, str(return_value))

    @command_root.command(name="ban", description=get("commands.ban.description"))
    @app_commands.check(interaction_check)
    @app_commands.describe(
        user=get("commands.ban.param_user"),
        reason=get("commands.ban.param_reason"),
    )
    async def command_ban(
        self,
        ctx: discord.Interaction,
        user: discord.User,
        reason: str | None = None,
    ) -> None:
        f_log = log.getChild("command.ban")
        f_log.debug(
            "/ban called by user=%s target=%s reason=%r",
            ctx.user.id if ctx.user else None,
            getattr(user, "id", None),
            reason,
        )
        mm_by_user = matchmaking_by_user_id()

        if ctx.user.id not in mm_by_user:
            await send_format_user_error(ctx, "ban_no_lobby")
            return
        matchmaker: MatchmakingInterface = mm_by_user[ctx.user.id]
        if matchmaker.creator.id != ctx.user.id:
            await send_format_user_error(ctx, "ban_not_creator")
            return

        return_value = await matchmaker.ban(user, reason)
        f_log.info(
            "Ban executed by %s on %s result=%r",
            ctx.user.id if ctx.user else None,
            getattr(user, "id", None),
            return_value,
        )
        await send_ephemeral_transient_text(ctx, str(return_value))

    @command_root.command(name="stats", description=get("commands.stats.description"))
    @app_commands.check(interaction_check)
    async def command_stats(self, ctx: discord.Interaction) -> None:
        f_log = log.getChild("command.stats")
        f_log.debug(f"/stats called: {contextify(ctx)}")

        server_count = len(self.bot.guilds)
        member_count = len(set(self.bot.get_all_members()))

        shard_id = ctx.guild.shard_id if ctx.guild else 0
        shard_ping = self.bot.latency
        shard_servers = len(
            [guild for guild in self.bot.guilds if guild.shard_id == shard_id],
        )

        container = CustomContainer(
            title=f"{get('embeds.stats.title')} {get_emoji_string('pointing')}",
            description=fmt("embeds.stats.description", managed_by=MANAGED_BY),
            color=INFO_COLOR,
        )

        container.add_field(
            name=get("embeds.stats.field_version"),
            value=f"v{VERSION}",
        )
        container.add_field(
            name=get("embeds.stats.field_discordpy"),
            value=f"{discord.__version__}",
        )
        container.add_field(
            name=get("embeds.stats.field_servers_overview"),
            value=(
                f"{server_count} servers · {len(GAME_TYPES)} games · "
                f"{len(self.bot.effective_owner_ids)} owners"
            ),
        )
        container.add_field(
            name=get("embeds.stats.field_shard_overview"),
            value=(
                f"#{shard_id} · {round(shard_ping * 1000, 2)} ms · "
                f"{shard_servers} servers"
            ),
        )
        container.add_field(
            name=get("embeds.stats.field_system"),
            value=f"{ramcheck.get_ram_usage_mb()} RAM",
        )
        reg = self.bot.container.registry
        container.add_field(
            name=get("embeds.stats.field_activity"),
            value=(
                f"{member_count} members · {len(reg.user_to_matchmaking)} queuing · "
                f"{len(reg.user_to_game)} in game"
            ),
            inline=False,
        )

        await response_send_message(ctx, **container_send_kwargs(container))

    @command_root.command(name="about", description=get("commands.about.description"))
    @app_commands.check(interaction_check)
    async def command_about(self, ctx: discord.Interaction) -> None:
        f_log = log.getChild("command.about")
        libraries = [
            "discord.py",
            "svg.py",
            "ruamel.yaml",
            "cairosvg",
            "emoji",
            "pillow",
            "psycopg",
            "psutil",
            "matplotlib",
        ]
        f_log.debug(f"/about called: {contextify(ctx)}")

        container = CustomContainer(title=get("embeds.about.title"), color=INFO_COLOR)
        container.add_field(
            name=get("embeds.about.field_credits"),
            value=get("embeds.about.credits_value"),
            inline=False,
        )
        container.add_field(
            name=get("embeds.about.field_source"),
            value=get("embeds.about.source_value"),
            inline=False,
        )
        container.add_field(
            name=get("embeds.about.field_libraries"),
            value=" · ".join(
                [f"[{lib}](https://pypi.org/project/{lib})" for lib in libraries],
            ),
            inline=False,
        )
        container.add_field(
            name=get("embeds.about.field_dev_time"),
            value=get("embeds.about.dev_timeline_value"),
        )
        container.set_footer(
            text=get("embeds.about.footer"),
            icon_url=get("brand.footer_icon"),
        )

        await response_send_message(ctx, **container_send_kwargs(container))

    @command_root.command(
        name="catalog",
        description=get("commands.catalog.description"),
    )
    @app_commands.check(interaction_check)
    @app_commands.describe(page=get("commands.catalog.param_page"))
    async def command_catalog(self, ctx: discord.Interaction, page: int = 1) -> None:
        f_log = log.getChild("command.catalog")
        f_log.debug(f"/catalog called with page={page}: {contextify(ctx)}")

        games_per_page = CATALOG_GAMES_PER_PAGE
        all_games = list(GAME_TYPES)
        total_pages = (len(all_games) + games_per_page - 1) // games_per_page

        if page < 1 or page > total_pages:
            page = 1

        container = self._build_catalog_container(
            page,
            total_pages,
            all_games,
            games_per_page,
        )

        view = PaginationView(
            guild_id=ctx.guild.id if ctx.guild else 0,
            user_id=ctx.user.id,
            current_page=page,
            max_pages=total_pages,
            body_text=container_to_markdown(container),
            callback_handler=lambda interaction, new_page: self._catalog_page_callback(
                interaction,
                new_page,
                total_pages,
                all_games,
                games_per_page,
            ),
        )
        await response_send_message(ctx, view=view)

    def _build_catalog_container(
        self,
        page: int,
        total_pages: int,
        all_games: list,
        games_per_page: int,
    ) -> CustomContainer:
        """Build the catalog container for a specific page."""
        start_idx = (page - 1) * games_per_page
        page_games = all_games[start_idx : start_idx + games_per_page]

        container = CustomContainer(
            title=fmt("embeds.catalog.title", name=NAME),
            color=INFO_COLOR,
        )
        container.description = fmt("embeds.catalog.description", count=len(GAME_TYPES))

        for game_id in page_games:
            meta = _GAME_METADATA[game_id]
            game_class = meta["class"]
            game_name = meta["name"]
            game_desc = meta["description"] or get("game_info.no_description")
            game_time = meta["time"] or get("game_info.unknown")
            game_difficulty = meta["difficulty"] or get("game_info.unknown")
            game_players = resolve_player_count(game_class)
            if game_players is None:
                game_players = get("game_info.unknown")
            game_emoji = get_game_emoji(game_id)
            if isinstance(game_players, list):
                player_text = fmt(
                    "game_info.players_range_format",
                    min=min(game_players),
                    max=max(game_players),
                )
            else:
                player_text = fmt("game_info.players_format", count=game_players)

            short_desc = f"{game_desc[:100]}{'...' if len(game_desc) > 100 else ''}"
            features = fmt(
                "embeds.catalog.game_features",
                roles=_catalog_bool_label(meta["supports_role_selection"]),
                replays=_catalog_bool_label(meta["supports_replays"]),
                bots=_catalog_bool_label(meta["supports_bots"]),
                options=_catalog_bool_label(meta["supports_lobby_options"]),
            )
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
                    features=features,
                    game_id=game_id,
                ),
                inline=False,
            )

        container.set_footer(
            text=fmt("embeds.catalog.footer", page=page, total=total_pages),
        )
        return container

    async def _catalog_page_callback(
        self,
        interaction: discord.Interaction,
        new_page: int,
        total_pages: int,
        all_games: list,
        games_per_page: int,
    ) -> None:
        """Callback for catalog pagination buttons."""
        container = self._build_catalog_container(
            new_page,
            total_pages,
            all_games,
            games_per_page,
        )
        view = PaginationView(
            guild_id=interaction.guild.id if interaction.guild else 0,
            user_id=interaction.user.id,
            current_page=new_page,
            max_pages=total_pages,
            body_text=container_to_markdown(container),
            callback_handler=lambda inter, pg: self._catalog_page_callback(
                inter,
                pg,
                total_pages,
                all_games,
                games_per_page,
            ),
        )
        await interaction.edit_original_response(view=view)

    def _sync_load_profile_container(
        self,
        user: discord.User,
        guild_id: int,
    ) -> tuple[CustomContainer | None, str | None]:
        """Build profile embed; runs in a worker thread (blocking DB)."""
        player = self._players.get_player(user.id, discord_user_db_label(user))
        if player is None:
            return None, "player_not_found"

        container = CustomContainer(
            title=fmt("embeds.profile.title", username=user.display_name),
            color=INFO_COLOR,
        )
        if _profile_supports_compact_avatar():
            container.set_thumbnail(url=user.display_avatar.url)

        match_history = self._matches.get_history_for_user(
            user.id,
            guild_id=guild_id,
            limit=5,
        )
        if match_history:
            history_lines = []
            for m in match_history:
                line = fmt(
                    "embeds.profile.match_format",
                    game_name=m.get("game_name", get("game_info.unknown")),
                    match_code=m.get("match_code", m.get("match_id", "?")),
                    outcome=_outcome_for_recent_match(m, user.id),
                )
                history_lines.append(line)
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
        return container, None

    @command_root.command(
        name="profile",
        description=get("commands.profile.description"),
    )
    @app_commands.check(interaction_check)
    @app_commands.describe(user=get("commands.profile.param_user"))
    async def command_profile(
        self,
        ctx: discord.Interaction,
        user: discord.User = None,
    ) -> None:
        f_log = log.getChild("command.profile")
        if user is None:
            user = ctx.user
        f_log.debug(f"/profile called for user={user.id}: {contextify(ctx)}")

        # Defer for database queries
        await ctx.response.defer()
        guild_id = ctx.guild.id if ctx.guild is not None else 0
        load_result = await run_in_thread(
            self._sync_load_profile_container,
            user,
            guild_id,
        )
        container, err = load_result
        if err == "player_not_found":
            await followup_send(
                ctx,
                content=format_user_error_message(
                    "player_not_found",
                    player_name=user.display_name,
                ),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        if container is None:
            return
        await followup_send(ctx, **container_send_kwargs(container))

    @command_root.command(
        name="history",
        description=get("commands.history.description"),
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
    ) -> None:
        f_log = log.getChild("command.history")
        if user is None:
            user = ctx.user
        page = max(page, 1)
        days = max(1, min(days, 365))

        f_log.debug(
            f"/history called for game={game}, user={user.id}, page={page}, days={days}: {contextify(ctx)}",
        )

        resolved_game, suggestion = _resolve_game_id_input(game)
        if resolved_game is None:
            message = fmt("history.unknown_game", game=game)
            if suggestion:
                message = f"{message}\n\n{fmt('commands.history.did_you_mean', game=suggestion)}"
            await response_send_message(
                ctx,
                message,
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        game = resolved_game

        game_db = await run_in_thread(self._games.get, game)
        if not game_db:
            await send_format_user_error(ctx, "game_not_registered")
            return

        game_name = _GAME_METADATA[game]["name"]

        container, _has_data, is_last_page = await run_in_thread(
            self._build_history_container,
            user,
            game_name,
            game_db.game_id,
            ctx.guild.id,
            page,
        )

        max_pages = page if is_last_page else page + 1
        container.set_footer(
            text=fmt("pagination.page_footer", page=page, max=max_pages),
        )
        view = PaginationView(
            guild_id=ctx.guild.id if ctx.guild else 0,
            user_id=ctx.user.id,
            current_page=page,
            max_pages=max_pages,
            body_text=container_to_markdown(container),
            callback_handler=lambda interaction, new_page: self._history_page_callback(
                interaction,
                user,
                game_name,
                game_db.game_id,
                new_page,
            ),
        )
        await response_send_message(ctx, view=view)

    def _build_history_container(
        self,
        user,
        game_name: str,
        game_id: int,
        guild_id: int,
        page: int,
    ):
        """
        Build history container for a specific page.

        Returns (container, has_data, is_last_page).
        """
        limit = HISTORY_PAGE_SIZE
        offset = (page - 1) * limit

        # Fetch one extra item to check if there are more pages
        match_history = self._matches.get_history_for_user(
            user.id,
            guild_id=guild_id,
            game_id=game_id,
            limit=limit + 1,
            offset=offset,
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
                summ = _match_summary_for_user(row.get("metadata"), user.id)
                summ_txt = f" — {summ}" if summ else ""
                mid = row.get("match_code") or row.get("match_id", "?")
                gkey = row.get("game_key") or "?"
                lines.append(
                    f"`{mid}` `{gkey}` · {rank_text}/{row.get('player_count', '?')} | "
                    f"{_history_status_label(row.get('status'))}{summ_txt}",
                )
            container.add_field(
                name=get("history.recent_matches"),
                value="\n".join(lines),
                inline=False,
            )
        else:
            container.add_field(
                name=get("history.recent_matches"),
                value=(
                    get("history.no_completed") if page == 1 else get("history.no_more")
                ),
                inline=False,
            )

        return container, has_data, is_last_page

    async def _history_page_callback(
        self,
        interaction: discord.Interaction,
        user,
        game_name: str,
        game_id: int,
        new_page: int,
    ) -> None:
        """Callback for history pagination buttons."""
        container, _has_data, is_last_page = await run_in_thread(
            self._build_history_container,
            user,
            game_name,
            game_id,
            interaction.guild.id,
            new_page,
        )
        max_pages = new_page if is_last_page else new_page + 1
        container.set_footer(
            text=fmt("pagination.page_footer", page=new_page, max=max_pages),
        )
        view = PaginationView(
            guild_id=interaction.guild.id if interaction.guild else 0,
            user_id=interaction.user.id,
            current_page=new_page,
            max_pages=max_pages,  # Dynamic max based on data
            body_text=container_to_markdown(container),
            callback_handler=lambda inter, pg: self._history_page_callback(
                inter,
                user,
                game_name,
                game_id,
                pg,
            ),
        )
        await interaction.edit_original_response(view=view)

    def _replay_game_label(self, game_id: int) -> str:
        g = self._games.get_by_id(game_id)
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
    ) -> None:
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
                inter,
                np,
                pages,
                match_id,
                game_label,
                global_summary,
                replay_display,
            ),
        )
        await interaction.edit_original_response(view=view)

    @command_root.command(name="replay", description=get("commands.replay.description"))
    @app_commands.describe(match_ref=get("commands.replay.param_match_ref"))
    @app_commands.guild_only()
    @app_commands.check(interaction_check)
    async def command_replay(
        self,
        ctx: discord.Interaction,
        match_ref: app_commands.Range[str, 1, 32],
    ) -> None:
        await ctx.response.defer(ephemeral=True)
        if ctx.guild is None:
            await followup_send(
                ctx,
                content=get("commands.set_channel.guild_only"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        raw = (match_ref or "").strip()
        match = await run_in_thread(
            resolve_match_for_replay,
            raw,
            ctx.guild.id,
            matches=self._matches,
        )
        if match is None:
            await followup_send(
                ctx,
                content=format_user_error_message("replay_not_found"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        match_id = match.match_id
        source = self._replay_source
        if source is None:
            await followup_send(
                ctx,
                content=format_user_error_message("replay_not_found"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        replay_ctx = await run_in_thread(
            replay_viewer.load_replay_context,
            match_id,
            source=source,
        )
        if replay_ctx is None:
            await followup_send(
                ctx,
                content=format_user_error_message("replay_not_found"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        replay_display = replay_ctx.replay_display
        events = replay_ctx.events
        if not events:
            await followup_send(
                ctx,
                content=fmt("commands.replay.no_data", match_display=replay_display),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        plugin_class = replay_ctx.plugin_class
        if replay_viewer.supports_replay_api(plugin_class) and plugin_class is not None:
            total_frames = replay_viewer.replay_frame_count(events)
            frame_layout = None
            if total_frames <= replay_viewer.PRECOMPUTE_FRAME_LIMIT:
                frames = replay_viewer.build_frames(
                    plugin_class,
                    events,
                    replay_ctx.players,
                    replay_ctx.match_options,
                    game_key=replay_ctx.game_key or plugin_class.metadata.key,
                )
                if frames:
                    replay_viewer.cache_precomputed_frames(replay_ctx.match_id, frames)
                    total_frames = len(frames)
                    frame_layout = frames[0]
            else:
                frame_layout = replay_viewer.frame_for_index(
                    match_id=replay_ctx.match_id,
                    frame_index=0,
                    plugin_class=plugin_class,
                    events=events,
                    players=replay_ctx.players,
                    match_options=replay_ctx.match_options,
                    game_key=replay_ctx.game_key or plugin_class.metadata.key,
                )

            if frame_layout is not None:
                title = fmt(
                    "commands.replay.title",
                    id=replay_ctx.replay_display,
                    game=replay_ctx.game_label,
                )
                view = ReplayViewerView(
                    match_id=replay_ctx.match_id,
                    owner_id=ctx.user.id,
                    frame_index=0,
                    total_frames=total_frames,
                    title=title,
                    global_summary=replay_ctx.global_summary,
                    frame_layout=frame_layout,
                )
                await followup_send(ctx, view=view, ephemeral=True)
                return

        lines = [format_replay_event_line(e) for e in events]
        pages = chunk_replay_lines(lines)
        game_label = replay_ctx.game_label
        replay_global = replay_ctx.global_summary
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
                inter,
                np,
                pages,
                match_id,
                game_label,
                replay_global,
                replay_display,
            ),
        )
        await followup_send(ctx, view=view, ephemeral=True)

    @command_replay.autocomplete("match_ref")
    async def replay_autocomplete(
        self,
        ctx: discord.Interaction,
        current: str,
    ) -> list[Choice[str]]:
        if ctx.guild is None:
            return []

        needle = (current or "").strip().lower()
        rows = await run_in_thread(
            self._matches.get_history_for_user,
            ctx.user.id,
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
        name="feedback",
        description=get("commands.feedback.description"),
    )
    @app_commands.describe(message=get("commands.feedback.param_message"))
    @app_commands.check(interaction_check)
    async def command_feedback(
        self,
        ctx: discord.Interaction,
        message: app_commands.Range[str, 1, 500],
    ) -> None:
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
                    target_id,
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
    async def command_forfeit(self, ctx: discord.Interaction) -> None:
        if ctx.channel.type != discord.ChannelType.private_thread:
            await response_send_message(
                ctx,
                get("forfeit.wrong_channel"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        game = self.bot.container.registry.games_by_thread_id.get(ctx.channel.id)
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
        await game.forfeit_player(ctx.user.id)
        await followup_send(
            ctx,
            fmt("forfeit.confirmed_loss", player=ctx.user.mention),
            ephemeral=True,
            delete_after=EPHEMERAL_DELETE_AFTER,
        )

    bot_group = app_commands.Group(
        name="bot",
        description=get("commands.bot.description"),
        parent=command_root,
    )

    @bot_group.command(name="list", description=get("commands.bot.list.description"))
    @app_commands.check(interaction_check)
    async def command_bot_list(self, ctx: discord.Interaction) -> None:
        f_log = log.getChild("command.bot.list")
        f_log.debug(f"/bot list called: {contextify(ctx)}")

        mm_by_user = matchmaking_by_user_id()
        if ctx.user.id not in mm_by_user:
            await send_ephemeral_transient_text(ctx, get("commands.bot.not_in_lobby"))
            return

        matchmaker: MatchmakingInterface = mm_by_user[ctx.user.id]

        # Check if game supports bots
        available_bots = getattr(matchmaker.metadata, "bots", {})
        if not available_bots:
            await send_ephemeral_transient_text(ctx, get("queue.bot_not_supported"))
            return

        # Build the list display
        lines = []
        lines.append(f"**{get('commands.bot.available_difficulties')}:**")
        for difficulty in sorted(available_bots.keys()):
            lines.append(f"  • `{difficulty}`")

        if matchmaker.bots:
            lines.append("")
            lines.append(f"**{get('commands.bot.queued_bots')}:**")
            for bot in matchmaker.bots:
                lines.append(f"  • {bot.display_name} ({bot.bot_difficulty})")
        else:
            lines.append("")
            lines.append(f"*{get('commands.bot.no_queued_bots')}*")

        await send_ephemeral_transient_text(ctx, "\n".join(lines))

    async def _autocomplete_bot_difficulty(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[Choice[str]]:
        mm_by_user = matchmaking_by_user_id()
        if interaction.user.id not in mm_by_user:
            return []

        matchmaker: MatchmakingInterface = mm_by_user[interaction.user.id]
        available_bots = getattr(matchmaker.metadata, "bots", {})

        choices = []
        for difficulty in sorted(available_bots.keys()):
            if current.lower() in difficulty.lower():
                choices.append(Choice(name=difficulty, value=difficulty))
        return choices[:25]

    async def _autocomplete_bot_name(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[Choice[str]]:
        mm_by_user = matchmaking_by_user_id()
        if interaction.user.id not in mm_by_user:
            return []

        matchmaker: MatchmakingInterface = mm_by_user[interaction.user.id]

        choices = []
        for bot in matchmaker.bots:
            bot_name = bot.display_name or "Bot"
            if current.lower() in bot_name.lower():
                choices.append(Choice(name=bot_name, value=bot_name))
        return choices[:25]

    @bot_group.command(
        name="add",
        description=get("commands.bot.add.description"),
    )
    @app_commands.check(interaction_check)
    @app_commands.autocomplete(difficulty=_autocomplete_bot_difficulty)
    @app_commands.describe(
        difficulty=get("commands.bot.add.param_difficulty"),
        number=get("commands.bot.add.param_number"),
    )
    async def command_bot_add(
        self,
        ctx: discord.Interaction,
        difficulty: str,
        number: int = 1,
    ) -> None:
        f_log = log.getChild("command.bot.add")
        f_log.debug(
            f"/bot add called: difficulty={difficulty}, number={number} {contextify(ctx)}",
        )

        mm_by_user = matchmaking_by_user_id()
        if ctx.user.id not in mm_by_user:
            await send_ephemeral_transient_text(ctx, get("commands.bot.not_in_lobby"))
            return

        matchmaker: MatchmakingInterface = mm_by_user[ctx.user.id]

        # Only lobby creator can add bots
        if matchmaker.creator.id != ctx.user.id:
            await send_ephemeral_transient_text(ctx, get("commands.bot.only_creator"))
            return

        # Validate number parameter
        if number < 1:
            await send_ephemeral_transient_text(
                ctx,
                get("commands.bot.add.error_invalid_number"),
            )
            return

        # Add the bots
        error = matchmaker.add_bot(difficulty, number=number)
        if error:
            await send_ephemeral_transient_text(ctx, str(error))
            return

        # Update the lobby display
        await matchmaker.update_embed()
        if number == 1:
            await send_ephemeral_transient_text(
                ctx,
                fmt("commands.bot.added", difficulty=difficulty),
            )
        else:
            await send_ephemeral_transient_text(
                ctx,
                fmt("commands.bot.added_multiple", difficulty=difficulty, count=number),
            )

    @bot_group.command(
        name="remove",
        description=get("commands.bot.remove.description"),
    )
    @app_commands.check(interaction_check)
    @app_commands.autocomplete(name=_autocomplete_bot_name)
    @app_commands.describe(
        name=get("commands.bot.remove.param_name"),
    )
    async def command_bot_remove(
        self,
        ctx: discord.Interaction,
        name: str,
    ) -> None:
        f_log = log.getChild("command.bot.remove")
        f_log.debug(
            f"/bot remove called: name={name} {contextify(ctx)}",
        )

        mm_by_user = matchmaking_by_user_id()
        if ctx.user.id not in mm_by_user:
            await send_ephemeral_transient_text(ctx, get("commands.bot.not_in_lobby"))
            return

        matchmaker: MatchmakingInterface = mm_by_user[ctx.user.id]

        # Only lobby creator can remove bots
        if matchmaker.creator.id != ctx.user.id:
            await send_ephemeral_transient_text(ctx, get("commands.bot.only_creator"))
            return

        # Remove the bot
        error = matchmaker.remove_bot(name)
        if error:
            await send_ephemeral_transient_text(ctx, str(error))
            return

        # Update the lobby display
        await matchmaker.update_embed()
        await send_ephemeral_transient_text(
            ctx,
            fmt("commands.bot.removed", name=name),
        )

    @command_root.command(
        name="settings",
        description=get("commands.settings.description"),
    )
    @app_commands.check(interaction_check)
    @app_commands.describe(
        private=get("commands.settings.param_private"),
    )
    async def command_settings(
        self,
        ctx: discord.Interaction,
        private: bool | None = None,
    ) -> None:
        f_log = log.getChild("command.settings")
        f_log.debug(
            f"/settings called: private={private} {contextify(ctx)}",
        )

        mm_by_user = matchmaking_by_user_id()
        if ctx.user.id not in mm_by_user:
            await send_ephemeral_transient_text(ctx, get("settings.not_in_matchmaking"))
            return

        matchmaker: MatchmakingInterface = mm_by_user[ctx.user.id]
        if matchmaker.creator.id != ctx.user.id:
            await send_ephemeral_transient_text(ctx, get("settings.only_creator"))
            return

        changes = []
        if private is not None and private != matchmaker.private:
            matchmaker.private = private
            changes.append(
                fmt(
                    "settings.changed_private",
                    value=get("settings.yes") if private else get("settings.no"),
                ),
            )

        if changes:
            await matchmaker.update_embed()
            await send_ephemeral_transient_text(
                ctx,
                get("settings.updated") + "\n" + "\n".join(changes),
            )
        else:
            await send_ephemeral_transient_text(ctx, get("settings.no_changes"))

    @command_root.command(
        name="set_channel",
        description=get("commands.set_channel.description"),
    )
    @app_commands.check(interaction_check)
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel=get("commands.set_channel.param_channel"))
    async def command_set_channel(
        self,
        ctx: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        if ctx.guild is None:
            await send_ephemeral_transient_text(
                ctx,
                get("commands.set_channel.guild_only"),
            )
            return
        await ctx.response.defer(ephemeral=True)
        if channel is None:
            await run_in_thread(
                self._guilds.merge_settings,
                ctx.guild.id,
                {"playcord_channel_id": None},
            )
            await followup_send(
                ctx,
                content=get("commands.set_channel.cleared"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        await run_in_thread(
            self._guilds.merge_settings,
            ctx.guild.id,
            {"playcord_channel_id": channel.id},
        )
        await followup_send(
            ctx,
            content=fmt("commands.set_channel.saved", channel=channel.mention),
            ephemeral=True,
            delete_after=EPHEMERAL_DELETE_AFTER,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GeneralCog(bot))
