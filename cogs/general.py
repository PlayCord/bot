import hashlib
import importlib
import logging
from datetime import datetime

from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from configuration.constants import *
from utils import database as db, embeds as _embeds, ramcheck
from utils.conversion import contextify
from utils.discord_utils import get_user_error_embed, interaction_check
from utils.emojis import get_emoji_string, get_game_emoji
from utils.graphs import generate_elo_chart
from utils.interfaces import MatchmakingInterface, user_in_active_game
from utils.locale import fmt, get, plural
from utils.views import HelpView, InviteView, PaginationView

CustomEmbed = _embeds.CustomEmbed
InviteEmbed = _embeds.InviteEmbed
HelpMainEmbed = getattr(_embeds, "HelpMainEmbed", _embeds.CustomEmbed)
HelpGettingStartedEmbed = getattr(_embeds, "HelpGettingStartedEmbed", _embeds.CustomEmbed)
HelpCommandsEmbed = getattr(_embeds, "HelpCommandsEmbed", _embeds.CustomEmbed)
HelpGameInfoEmbed = getattr(_embeds, "HelpGameInfoEmbed", _embeds.CustomEmbed)

log = logging.getLogger(LOGGING_ROOT)


def _ordinal(value: int) -> str:
    if value is None:
        return "?"
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


async def autocomplete_game_id(ctx: discord.Interaction, current: str) -> list[Choice[str]]:
    query = current.lower().strip()
    matches = []

    for game_id, (module_name, class_name) in GAME_TYPES.items():
        game_class = getattr(importlib.import_module(module_name), class_name)
        print(game_class.__dict__)
        description = str(getattr(game_class, "summary", None))
        if description is not None:
            description = " (" + description + ")"
        else:
            description = ""
        display_name = str(getattr(game_class, "name", game_id)) + description

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
async def command_play(ctx: discord.Interaction, game: str, rated: bool = True, private: bool = False) -> None:
    selected_game = game.strip()
    game_type = selected_game.lower()
    if game_type not in GAME_TYPES:
        embed = get_user_error_embed("game_invalid", game=selected_game)
        await ctx.response.send_message(embed=embed, ephemeral=True)
        return

    from cogs.games import begin_game

    await begin_game(ctx, game_type, rated=rated, private=private)


async def autocomplete_invite_bot(ctx: discord.Interaction, current: str) -> list[Choice[str]]:
    if user_in_active_game(ctx.user.id):
        return []

    id_matchmaking = {p.id: q for p, q in IN_MATCHMAKING.items()}
    if ctx.user.id not in id_matchmaking:
        return []

    matchmaker: MatchmakingInterface = id_matchmaking[ctx.user.id]
    available_bots = getattr(matchmaker.game, "bots", {})
    if not available_bots:
        return []

    query = current.lower().strip()
    matches = []
    for difficulty, bot in available_bots.items():
        description = getattr(bot, "description", "")
        label = f"{difficulty.title()} ({description})" if description else difficulty.title()
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
        guild_only=False
    )

    @command_root.command(name="invite", description=get("commands.invite.description"))
    @app_commands.describe(
        user=get("commands.invite.param_user"),
        game=get("commands.invite.param_game"),
        user2=get("commands.invite.param_user2"),
        user3=get("commands.invite.param_user3"),
        user4=get("commands.invite.param_user4"),
        user5=get("commands.invite.param_user5"),
        bot1=get("commands.invite.param_bot1"),
        bot2=get("commands.invite.param_bot2"),
        bot3=get("commands.invite.param_bot3"),
        bot4=get("commands.invite.param_bot4"),
        bot5=get("commands.invite.param_bot5"),
    )
    @app_commands.autocomplete(
        game=autocomplete_game_id,
        bot1=autocomplete_invite_bot,
        bot2=autocomplete_invite_bot,
        bot3=autocomplete_invite_bot,
        bot4=autocomplete_invite_bot,
        bot5=autocomplete_invite_bot,
    )
    async def command_invite(self, ctx: discord.Interaction,
                             user: discord.User = None,
                             game: str = None,
                             user2: discord.User = None,
                             user3: discord.User = None,
                             user4: discord.User = None,
                             user5: discord.User = None,
                             bot1: str = None,
                             bot2: str = None,
                             bot3: str = None,
                             bot4: str = None,
                             bot5: str = None) -> None:
        f_log = log.getChild("command.invite")
        f_log.debug(f"/invite called: {contextify(ctx)}")
        invited_users = [candidate for candidate in [user, user2, user3, user4, user5] if candidate is not None]
        requested_bots = [candidate for candidate in [bot1, bot2, bot3, bot4, bot5] if candidate is not None]

        if not invited_users and not requested_bots:
            if ctx.response.is_done():
                await ctx.followup.send(get("matchmaking.invite_no_targets"), ephemeral=True)
            else:
                await ctx.response.send_message(get("matchmaking.invite_no_targets"), ephemeral=True)
            return

        id_matchmaking = {p.id: q for p, q in IN_MATCHMAKING.items()}

        if ctx.user.id not in id_matchmaking:
            if user_in_active_game(ctx.user.id):
                embed = get_user_error_embed("already_in_game_other_server")
                await ctx.response.send_message(embed=embed, ephemeral=True)
                return

            if game is None:
                embed = get_user_error_embed("no_active_lobby")
                await ctx.response.send_message(embed=embed, ephemeral=True)
                return

            if game not in GAME_TYPES:
                embed = get_user_error_embed("game_invalid", game=game)
                await ctx.response.send_message(embed=embed, ephemeral=True)
                return

            # Start a new matchmaking lobby
            from cogs.games import begin_game
            await begin_game(ctx, game)

            # Need to wait a bit or re-fetch to get the new matchmaker
            # Actually, handle the rest of it after begin_game finishes and we find the matchmaker
            id_matchmaking = {p.id: q for p, q in IN_MATCHMAKING.items()}
            if ctx.user.id not in id_matchmaking:
                # It might take a moment or begin_game failed
                return

        matchmaker: MatchmakingInterface = id_matchmaking[ctx.user.id]
        from cogs.games import add_matchmaking_bot

        if matchmaker.private and matchmaker.creator.id != ctx.user.id:
            embed = get_user_error_embed("invite_not_creator_private")
            await ctx.response.send_message(embed=embed, ephemeral=True)
            f_log.debug(f"/invite rejected: not creator. {contextify(ctx)}")
            return

        for difficulty in requested_bots:
            await add_matchmaking_bot(ctx, difficulty)

        game_type = matchmaker.game.name
        failed_invites = {}
        for invited_user in invited_users:
            if invited_user not in matchmaker.message.guild.members:
                failed_invites[invited_user] = get("matchmaking.invite_failed_not_in_server")
                continue
            if invited_user.id in [p.id for p in matchmaker.queued_players]:
                failed_invites[invited_user] = get("matchmaking.invite_failed_already_queued")
                continue
            if user_in_active_game(invited_user.id):
                failed_invites[invited_user] = get("matchmaking.invite_failed_in_game")
                continue
            if invited_user.bot:
                failed_invites[invited_user] = get("matchmaking.invite_failed_bot")
                continue

            # Invitation
            embed = InviteEmbed(inviter=ctx.user, game_type=game_type, guild_name=matchmaker.message.guild.name)

            await invited_user.send(embed=embed,
                                    view=InviteView(join_button_id=BUTTON_PREFIX_INVITE + str(matchmaker.message.id),
                                                    game_link=matchmaker.message.jump_url))
            continue

        if not invited_users:
            return

        if not len(failed_invites):
            f_log.debug(f"/invite success: {len(invited_users)} succeeded, 0 failed. {contextify(ctx)}")
            if ctx.response.is_done():
                await ctx.followup.send(get("success.invites_sent"), ephemeral=True)
            else:
                await ctx.response.send_message(get("success.invites_sent"), ephemeral=True)
            return
        elif len(failed_invites) == len(invited_users):
            message = get("matchmaking.invites_failed_all")
        else:
            message = get("matchmaking.invites_failed_partial")
        f_log.debug(f"/invite partial or no success: {len(invited_users) - len(failed_invites)} succeeded,"
                    f" {len(failed_invites)} failed. {contextify(ctx)}")
        final = message + "\n"
        for fail in failed_invites:
            final += f"{fail.mention} - {failed_invites[fail]}\n"

        if ctx.response.is_done():
            await ctx.followup.send(final, ephemeral=True)
        else:
            await ctx.response.send_message(final, ephemeral=True)

    @command_root.command(name="kick", description=get("commands.kick.description"))
    @app_commands.describe(
        user=get("commands.kick.param_user"),
        reason=get("commands.kick.param_reason"),
    )
    async def command_kick(self, ctx: discord.Interaction, user: discord.User, reason: str = None):
        f_log = log.getChild("command.kick")
        id_matchmaking = {p.id: q for p, q in IN_MATCHMAKING.items()}

        if ctx.user.id not in id_matchmaking:
            embed = get_user_error_embed("kick_no_lobby")
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return
        matchmaker: MatchmakingInterface = id_matchmaking[ctx.user.id]
        if matchmaker.creator.id != ctx.user.id:
            embed = get_user_error_embed("kick_not_creator")
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return

        return_value = await matchmaker.kick(user, reason)
        await ctx.response.send_message(return_value, ephemeral=True)

    @command_root.command(name="ban", description=get("commands.ban.description"))
    @app_commands.describe(
        user=get("commands.ban.param_user"),
        reason=get("commands.ban.param_reason"),
    )
    async def command_ban(self, ctx: discord.Interaction, user: discord.User, reason: str = None):
        f_log = log.getChild("command.ban")
        id_matchmaking = {p.id: q for p, q in IN_MATCHMAKING.items()}

        if ctx.user.id not in id_matchmaking:
            embed = get_user_error_embed("ban_no_lobby")
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return
        matchmaker: MatchmakingInterface = id_matchmaking[ctx.user.id]
        if matchmaker.creator.id != ctx.user.id:
            embed = get_user_error_embed("ban_not_creator")
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return

        return_value = await matchmaker.ban(user, reason)
        await ctx.response.send_message(return_value, ephemeral=True)

    @command_root.command(name="stats", description=get("commands.stats.description"))
    async def command_stats(self, ctx: discord.Interaction):
        f_log = log.getChild("command.stats")
        f_log.debug(f"/stats called: {contextify(ctx)}")

        server_count = len(self.bot.guilds)
        member_count = len(set(self.bot.get_all_members()))

        shard_id = ctx.guild.shard_id
        shard_ping = self.bot.latency
        shard_servers = len([guild for guild in self.bot.guilds if guild.shard_id == shard_id])

        embed = CustomEmbed(
            title=f'{get("embeds.stats.title")} {get_emoji_string("pointing")}',
            description=fmt("embeds.stats.description", managed_by=MANAGED_BY),
            color=INFO_COLOR
        )

        embed.add_field(name=get("embeds.stats.field_version"), value=VERSION)
        embed.add_field(name=get("embeds.stats.field_discordpy"), value=discord.__version__)
        embed.add_field(name=get("embeds.stats.field_games_loaded"), value=len(GAME_TYPES))
        embed.add_field(name=get("embeds.stats.field_total_servers"), value=server_count)
        embed.add_field(name=get("embeds.stats.field_owners"), value=len(OWNERS))
        embed.add_field(name=get("embeds.stats.field_ram"), value=ramcheck.get_ram_usage_mb())
        embed.add_field(name=get("embeds.stats.field_shard_id"), value=shard_id)
        embed.add_field(name=get("embeds.stats.field_shard_ping"),
                        value=fmt("format.ping_ms", ping=round(shard_ping * 100, 2)))
        embed.add_field(name=get("embeds.stats.field_shard_servers"), value=shard_servers)
        embed.add_field(name=f'{get_emoji_string("user")} {get("embeds.stats.field_users")}', value=member_count)
        embed.add_field(name=get("embeds.stats.field_in_matchmaking"), value=len(IN_MATCHMAKING))
        embed.add_field(name=get("embeds.stats.field_in_game"), value=len(IN_GAME))

        await ctx.response.send_message(embed=embed)

    @command_root.command(name="about", description=get("commands.about.description"))
    async def command_about(self, ctx: discord.Interaction):
        f_log = log.getChild("command.about")
        libraries = ["discord.py", "svg.py", "ruamel.yaml", "cairosvg", "trueskill", "mpmath"]
        f_log.debug(f"/about called: {contextify(ctx)}")

        embed = CustomEmbed(title=get("embeds.about.title"), color=INFO_COLOR)
        embed.add_field(name=get("embeds.about.field_bot_by"), value="[@quantumbagel](https://github.com/quantumbagel)")
        embed.add_field(name=get("embeds.about.field_source"), value="[here](https://github.com/PlayCord/bot)")
        embed.add_field(name=get("embeds.about.field_pfp"), value="[@soldship](https://github.com/quantumsoldship)")
        embed.add_field(name=get("embeds.about.field_inspiration"),
                        value="[LoRiggio (Liar's Dice Bot)](https://github.com/Pixelz22/LoRiggioDev) by [@Pixelz22](https://github.com/Pixelz22)",
                        inline=True)
        embed.add_field(name=get("embeds.about.field_libraries"),
                        value="\n".join([f"[{lib}](https://pypi.org/project/{lib})" for lib in libraries]),
                        inline=False)
        embed.add_field(name=get("embeds.about.field_dev_time"),
                        value="October 2024 - March 2025\nMarch 2026 - Present")
        embed.set_footer(text=get("embeds.about.footer"))

        await ctx.response.send_message(embed=embed)

    @command_root.command(name="help", description=get("commands.help.description"))
    @app_commands.describe(topic=get("commands.help.param_topic"))
    @app_commands.choices(topic=[
        Choice(name=get("commands.help.choice_getting_started"), value="getting_started"),
        Choice(name=get("commands.help.choice_commands"), value="commands"),
        Choice(name=get("commands.help.choice_games"), value="games"),
    ])
    async def command_help(self, ctx: discord.Interaction, topic: str = None):
        f_log = log.getChild("command.help")
        f_log.debug(f"/help called with topic={topic}: {contextify(ctx)}")

        # Determine which embed to show based on topic
        if topic == "getting_started":
            embed = HelpGettingStartedEmbed()
            section = "getting_started"
        elif topic == "commands":
            embed = HelpCommandsEmbed()
            section = "commands"
        elif topic == "games":
            # Build games overview
            embed = await self._build_help_games_embed()
            section = "games"
        else:
            embed = HelpMainEmbed()
            section = "main"

        view = HelpView(user_id=ctx.user.id, current_section=section)
        await ctx.response.send_message(embed=embed, view=view)

    async def _build_help_games_embed(self):
        """Build a quick games overview embed for help menu."""
        embed = CustomEmbed(
            title=get("help.games_overview.title"),
            description=get("help.games_overview.description"),
            color=INFO_COLOR
        )

        games_text = []
        for game_id, (module_name, class_name) in list(GAME_TYPES.items())[:8]:
            game_class = getattr(importlib.import_module(module_name), class_name)
            game_name = getattr(game_class, 'name', game_id)
            games_text.append(f"• **{game_name}** (`/play {game_id}`)")

        if len(GAME_TYPES) > 8:
            games_text.append(fmt("help.games_overview.more_games", count=len(GAME_TYPES) - 8))

        embed.add_field(
            name=get("help.games_overview.field_games"),
            value="\n".join(games_text),
            inline=False
        )

        embed.add_field(
            name=get("help.games_overview.field_tip"),
            value=get("help.games_overview.tip_value"),
            inline=False
        )

        return embed

    @command_root.command(name="learn", description=get("commands.learn.description"))
    @app_commands.describe(game=get("commands.learn.param_game"))
    @app_commands.autocomplete(game=autocomplete_game_id)
    async def command_learn(self, ctx: discord.Interaction, game: str):
        f_log = log.getChild("command.learn")
        f_log.debug(f"/learn called for game={game}: {contextify(ctx)}")

        if game not in GAME_TYPES:
            embed = get_user_error_embed("learn_game_not_found", game=game)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return

        game_info = GAME_TYPES[game]
        game_class = getattr(importlib.import_module(game_info[0]), game_info[1])

        embed = HelpGameInfoEmbed(game, game_class)
        await ctx.response.send_message(embed=embed)

    @command_root.command(name="leaderboard", description=get("commands.leaderboard.description"))
    @app_commands.describe(
        game=get("commands.leaderboard.param_game"),
        scope=get("commands.leaderboard.param_scope"),
        page=get("commands.leaderboard.param_page"),
    )
    @app_commands.choices(scope=[Choice(name=get("commands.leaderboard.choice_server"), value="server"),
                                 Choice(name=get("commands.leaderboard.choice_global"), value="global")])
    @app_commands.autocomplete(game=autocomplete_game_id)
    async def command_leaderboard(self, ctx: discord.Interaction, game: str, scope: str = "server", page: int = 1):
        f_log = log.getChild("command.leaderboard")
        f_log.debug(f"/leaderboard called for game={game}, scope={scope}, page={page}: {contextify(ctx)}")

        if game not in GAME_TYPES:
            embed = get_user_error_embed("game_invalid", game=game)
            await ctx.response.send_message(embed=embed, ephemeral=True)
            return

        # Defer response for database query (shows "thinking...")
        await ctx.response.defer()

        game_class = getattr(importlib.import_module(GAME_TYPES[game][0]), GAME_TYPES[game][1])
        game_name = game_class.name
        game_db = db.database.get_game(game)
        if not game_db:
            await ctx.followup.send(get("errors.game_not_registered.value"), ephemeral=True)
            return

        if page < 1:
            page = 1

        limit = 10

        embed, has_data, is_last_page = self._build_leaderboard_embed(game, game_name, game_db.game_id, scope,
                                                                      ctx.guild, page, limit)

        # If no data on this page and page > 1, go back to page 1
        if not has_data and page > 1:
            page = 1
            embed, has_data, is_last_page = self._build_leaderboard_embed(game, game_name, game_db.game_id, scope,
                                                                          ctx.guild, page, limit)

        max_pages = page if is_last_page else page + 1
        embed.set_footer(text=fmt("embeds.leaderboard.footer", page=page, max=max_pages))

        params_hash = hashlib.md5(f"{game}:{scope}".encode()).hexdigest()[:8]
        view = PaginationView(
            command="leaderboard",
            guild_id=ctx.guild.id if ctx.guild else 0,
            user_id=ctx.user.id,
            current_page=page,
            max_pages=max_pages,
            params_hash=params_hash,
            callback_handler=lambda interaction, new_page: self._leaderboard_page_callback(
                interaction, game, game_name, game_db.game_id, scope, new_page, limit, params_hash
            )
        )
        await ctx.followup.send(embed=embed, view=view)

    def _build_leaderboard_embed(self, game: str, game_name: str, game_id: int, scope: str,
                                 guild, page: int, limit: int):
        """Build the leaderboard embed for a specific page. Returns (embed, has_data, is_last_page)."""
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
            # Fetch one extra item to check if there are more pages
            leaderboard_data = db.database.get_leaderboard(
                guild.id,
                game_id,
                limit=limit + 1,
                offset=offset,
                min_matches=1,
            )
            scope_text = fmt("leaderboard.scope_server", guild_name=guild.name)

        title_key = "embeds.leaderboard.title_global" if scope == "global" else "embeds.leaderboard.title_server"
        embed = CustomEmbed(title=fmt(title_key, game_name=game_name), color=INFO_COLOR)
        embed.description = scope_text

        has_data = bool(leaderboard_data)
        # If we got more than limit items, there are more pages
        is_last_page = len(leaderboard_data) <= limit

        # Only use the first 'limit' items for display
        display_data = leaderboard_data[:limit]

        if not display_data:
            embed.add_field(name=get("leaderboard.no_data_name"),
                            value=get("embeds.leaderboard.no_players") if page == 1 else get(
                                "embeds.leaderboard.no_more_players"),
                            inline=False)
        else:
            rankings = []
            for i, entry in enumerate(display_data, start=offset + 1):
                user_id = entry['user_id']
                conservative = entry.get('conservative_rating', entry.get('mu', 0))
                mu = entry.get('mu', 0)
                matches = entry.get('matches_played', 0)
                medal = get("format.rank_medal_1") if i == 1 else \
                    get("format.rank_medal_2") if i == 2 else \
                        get("format.rank_medal_3") if i == 3 else \
                            fmt("format.rank_number", rank=i)
                rankings.append(
                    fmt("embeds.leaderboard.ranking_format",
                        medal=medal,
                        user_id=user_id,
                        conservative=round(conservative),
                        mu=round(mu),
                        matches=matches,
                        games_word=plural("game", matches))
                )
            embed.add_field(name=get("embeds.leaderboard.field_rankings"), value="\n".join(rankings), inline=False)

        return embed, has_data, is_last_page

    async def _leaderboard_page_callback(self, interaction: discord.Interaction, game: str, game_name: str,
                                         game_id: int, scope: str, new_page: int,
                                         limit: int, params_hash: str):
        """Callback for leaderboard pagination buttons."""
        embed, has_data, is_last_page = self._build_leaderboard_embed(game, game_name, game_id, scope,
                                                                      interaction.guild,
                                                                      new_page, limit)
        max_pages = new_page if is_last_page else new_page + 1
        embed.set_footer(text=fmt("embeds.leaderboard.footer", page=new_page, max=max_pages))
        view = PaginationView(
            command="leaderboard",
            guild_id=interaction.guild.id if interaction.guild else 0,
            user_id=interaction.user.id,
            current_page=new_page,
            max_pages=max_pages,  # Dynamic max based on data
            params_hash=params_hash,
            callback_handler=lambda inter, pg: self._leaderboard_page_callback(
                inter, game, game_name, game_id, scope, pg, limit, params_hash
            )
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @command_root.command(name="catalog", description=get("commands.catalog.description"))
    @app_commands.describe(page=get("commands.catalog.param_page"))
    async def command_catalog(self, ctx: discord.Interaction, page: int = 1):
        f_log = log.getChild("command.catalog")
        f_log.debug(f"/catalog called with page={page}: {contextify(ctx)}")

        games_per_page = 3
        all_games = list(GAME_TYPES.keys())
        total_pages = (len(all_games) + games_per_page - 1) // games_per_page

        if page < 1 or page > total_pages:
            page = 1

        embed = self._build_catalog_embed(page, total_pages, all_games, games_per_page)

        params_hash = hashlib.md5(f"catalog".encode()).hexdigest()[:8]
        view = PaginationView(
            command="catalog",
            guild_id=ctx.guild.id if ctx.guild else 0,
            user_id=ctx.user.id,
            current_page=page,
            max_pages=total_pages,
            params_hash=params_hash,
            callback_handler=lambda interaction, new_page: self._catalog_page_callback(
                interaction, new_page, total_pages, all_games, games_per_page, params_hash
            )
        )
        await ctx.response.send_message(embed=embed, view=view)

    def _build_catalog_embed(self, page: int, total_pages: int, all_games: list, games_per_page: int) -> CustomEmbed:
        """Build the catalog embed for a specific page."""
        start_idx = (page - 1) * games_per_page
        page_games = all_games[start_idx:start_idx + games_per_page]

        embed = CustomEmbed(title=fmt("embeds.catalog.title", name=NAME), color=INFO_COLOR)
        embed.description = fmt("embeds.catalog.description", count=len(GAME_TYPES))

        for game_id in page_games:
            game_info = GAME_TYPES[game_id]
            game_class = getattr(importlib.import_module(game_info[0]), game_info[1])
            game_name = getattr(game_class, 'name', game_id)
            game_desc = getattr(game_class, 'description', get("help.game_info.no_description"))
            game_time = getattr(game_class, 'time', get("help.game_info.unknown"))
            game_difficulty = getattr(game_class, 'difficulty', get("help.game_info.unknown"))
            game_players = getattr(game_class, 'players', get("help.game_info.unknown"))
            game_emoji = get_game_emoji(game_id)
            if isinstance(game_players, list):
                player_text = fmt("help.game_info.players_range_format", min=min(game_players), max=max(game_players))
            else:
                player_text = fmt("help.game_info.players_format", count=game_players)

            short_desc = f"{game_desc[:100]}{'...' if len(game_desc) > 100 else ''}"
            embed.add_field(
                name=fmt("embeds.catalog.game_field_format", emoji=game_emoji, game_name=game_name),
                value=fmt("embeds.catalog.game_value_format",
                          description=short_desc,
                          time=game_time,
                          players=player_text,
                          difficulty=game_difficulty,
                          game_id=game_id),
                inline=False
            )

        embed.set_footer(text=fmt("embeds.catalog.footer", page=page, total=total_pages))
        return embed

    async def _catalog_page_callback(self, interaction: discord.Interaction, new_page: int,
                                     total_pages: int, all_games: list, games_per_page: int, params_hash: str):
        """Callback for catalog pagination buttons."""
        embed = self._build_catalog_embed(new_page, total_pages, all_games, games_per_page)
        view = PaginationView(
            command="catalog",
            guild_id=interaction.guild.id if interaction.guild else 0,
            user_id=interaction.user.id,
            current_page=new_page,
            max_pages=total_pages,
            params_hash=params_hash,
            callback_handler=lambda inter, pg: self._catalog_page_callback(
                inter, pg, total_pages, all_games, games_per_page, params_hash
            )
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @command_root.command(name="profile", description=get("commands.profile.description"))
    @app_commands.describe(user=get("commands.profile.param_user"))
    async def command_profile(self, ctx: discord.Interaction, user: discord.User = None):
        f_log = log.getChild("command.profile")
        if user is None: user = ctx.user
        f_log.debug(f"/profile called for user={user.id}: {contextify(ctx)}")

        # Defer for database queries
        await ctx.response.defer()

        player = db.database.get_player(user, ctx.guild.id)
        if player is None:
            embed = get_user_error_embed("player_not_found", player_name=user.display_name)
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        embed = CustomEmbed(title=fmt("embeds.profile.title", username=user.display_name), color=INFO_COLOR)
        embed.set_thumbnail(url=user.display_avatar.url)

        game_stats = []
        for game_id in GAME_TYPES:
            game_info = GAME_TYPES[game_id]
            game_class = getattr(importlib.import_module(game_info[0]), game_info[1])
            game_name = getattr(game_class, 'name', game_id)
            rating_info = db.database.get_user_game_ratings(user.id, ctx.guild.id, game_id)
            if rating_info and rating_info.get('matches_played', 0) > 0:
                mu = rating_info.get('mu', 1000)
                matches = rating_info.get('matches_played', 0)

                # Check for global rank
                game_db = db.database.get_game(game_id)
                if game_db:
                    global_rank = db.database.get_user_global_rank(user.id, game_db.game_id)
                    if global_rank is not None and global_rank <= 100:
                        rank_badge = get("format.rank_badge_1") if global_rank == 1 else \
                            get("format.rank_badge_top3") if global_rank <= 3 else \
                                get("format.rank_badge_top10") if global_rank <= 10 else ""
                        game_stats.append(
                            fmt("embeds.profile.rating_format_ranked",
                                game_name=game_name,
                                rating=round(mu),
                                matches=matches,
                                games_word=plural("game", matches),
                                badge=rank_badge,
                                rank=global_rank)
                        )
                    else:
                        game_stats.append(
                            fmt("embeds.profile.rating_format",
                                game_name=game_name,
                                rating=round(mu),
                                matches=matches,
                                games_word=plural("game", matches))
                        )
                else:
                    game_stats.append(
                        fmt("embeds.profile.rating_format",
                            game_name=game_name,
                            rating=round(mu),
                            matches=matches,
                            games_word=plural("game", matches))
                    )

        if game_stats:
            embed.add_field(name=get("embeds.profile.field_ratings"), value="\n".join(game_stats), inline=False)
        else:
            embed.add_field(name=get("embeds.profile.field_ratings"), value=get("embeds.profile.field_ratings_empty"),
                            inline=False)

        match_history = db.database.get_user_match_history(user.id, ctx.guild.id, limit=5)
        if match_history:
            history_lines = [
                fmt("embeds.profile.match_format",
                    game_name=m.get('game_name', get("help.game_info.unknown")),
                    ranking=_ordinal(m.get('final_ranking')),
                    player_count=m.get('player_count', '?'),
                    seat=m.get('player_number', '?'),
                    rated_status=get("history.rated") if m.get('is_rated', True) else get("history.casual"),
                    delta=f"{'+' if m.get('mu_delta', 0) >= 0 else ''}{round(m.get('mu_delta', 0))}")
                for m in match_history]
            embed.add_field(name=get("embeds.profile.field_recent_matches"), value="\n".join(history_lines),
                            inline=False)
        else:
            embed.add_field(name=get("embeds.profile.field_recent_matches"),
                            value=get("embeds.profile.field_recent_matches_empty"), inline=False)

        total_matches = db.database.count_matches_for_user(user.id, ctx.guild.id)
        embed.add_field(
            name=get("embeds.profile.field_total_games"),
            value=f"{total_matches} {plural('game', total_matches)}",
            inline=True,
        )
        await ctx.response.send_message(embed=embed)

    @command_root.command(name="history", description=get("commands.history.description"))
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

        f_log.debug(f"/history called for game={game}, user={user.id}, page={page}, days={days}: {contextify(ctx)}")

        if game not in GAME_TYPES:
            await ctx.response.send_message(
                fmt("history.unknown_game", game=game),
                ephemeral=True,
            )
            return

        game_db = db.database.get_game(game)
        if not game_db:
            await ctx.response.send_message(get("errors.game_not_registered.value"), ephemeral=True)
            return

        game_class = getattr(importlib.import_module(GAME_TYPES[game][0]), GAME_TYPES[game][1])
        game_name = getattr(game_class, 'name', game)

        embed, chart_file, has_data, is_last_page = self._build_history_embed(
            user, game_name, game_db.game_id, ctx.guild.id, page, days, f_log
        )

        max_pages = page if is_last_page else page + 1
        embed.set_footer(text=fmt("pagination.page_footer", page=page, max=max_pages))
        params_hash = hashlib.md5(f"{game}:{user.id}:{days}".encode()).hexdigest()[:8]
        view = PaginationView(
            command="history",
            guild_id=ctx.guild.id if ctx.guild else 0,
            user_id=ctx.user.id,
            current_page=page,
            max_pages=max_pages,
            params_hash=params_hash,
            callback_handler=lambda interaction, new_page: self._history_page_callback(
                interaction, user, game_name, game_db.game_id, new_page, days, params_hash, f_log
            )
        )
        if chart_file:
            await ctx.response.send_message(embed=embed, file=chart_file, view=view)
        else:
            await ctx.response.send_message(embed=embed, view=view)

    def _build_history_embed(self, user, game_name: str, game_id: int, guild_id: int,
                             page: int, days: int, f_log):
        """Build history embed for a specific page. Returns (embed, chart_file, has_data, is_last_page)."""
        limit = 8
        offset = (page - 1) * limit

        # Fetch one extra item to check if there are more pages
        match_history = db.database.get_user_match_history(
            user.id,
            guild_id,
            game_id=game_id,
            limit=limit + 1,
            offset=offset,
        )
        rating_history = db.database.get_rating_history(user.id, guild_id, game_id, days=days)

        embed = CustomEmbed(title=fmt("history.embed_title", user=user.display_name, game=game_name), color=INFO_COLOR)
        embed.set_thumbnail(url=user.display_avatar.url)

        has_data = bool(match_history)
        # If we got more than limit items, there are more pages
        is_last_page = len(match_history) <= limit

        # Only use the first 'limit' items for display
        display_history = match_history[:limit]

        if display_history:
            lines = []
            for row in display_history:
                rank_text = _ordinal(row.get('final_ranking'))
                delta = row.get('mu_delta', 0)
                lines.append(
                    f"{rank_text}/{row.get('player_count', '?')} | {fmt('history.seat', seat=row.get('player_number', '?'))}"
                    f" | {get('history.rated') if row.get('is_rated', True) else get('history.casual')}"
                    f" | {'+' if delta >= 0 else ''}{round(delta)}"
                )
            embed.add_field(name=get("history.recent_matches"), value="\n".join(lines), inline=False)
        else:
            embed.add_field(name=get("history.recent_matches"),
                            value=get("history.no_completed") if page == 1 else get("history.no_more"),
                            inline=False)

        # Generate matplotlib chart if rating history exists (only on first page for performance)
        chart_file = None
        if rating_history and page == 1:
            ascending = list(reversed(rating_history))
            points = [ascending[0].get('mu_before', MU)] + [row.get('mu_after', MU) for row in ascending]
            timestamps = [datetime.fromisoformat(str(ascending[0].get('timestamp')))] + \
                         [datetime.fromisoformat(str(row.get('timestamp'))) for row in ascending]

            rating_data = list(zip(timestamps, points))

            try:
                chart_buffer = generate_elo_chart(
                    rating_data,
                    title=fmt("history.chart_title", user=user.display_name, game=game_name),
                    figsize=(10, 6),
                    dpi=100
                )
                chart_file = discord.File(chart_buffer, filename="rating_chart.png")
                embed.set_image(url="attachment://rating_chart.png")

                delta_total = points[-1] - points[0]
                embed.add_field(
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
                embed.add_field(
                    name=fmt("history.rating_trend_name", days=days),
                    value=(
                        f"{get('history.start')}: {round(points[0])} → {get('history.end')}: {round(points[-1])} "
                        f"({'+' if delta_total >= 0 else ''}{round(delta_total)})"
                    ),
                    inline=False,
                )
        elif page == 1:
            embed.add_field(name=fmt("history.rating_trend_name", days=days), value=get("history.no_rating_period"),
                            inline=False)

        return embed, chart_file, has_data, is_last_page

    async def _history_page_callback(self, interaction: discord.Interaction, user, game_name: str,
                                     game_id: int, new_page: int, days: int, params_hash: str, f_log):
        """Callback for history pagination buttons."""
        embed, chart_file, has_data, is_last_page = self._build_history_embed(
            user, game_name, game_id, interaction.guild.id, new_page, days, f_log
        )
        max_pages = new_page if is_last_page else new_page + 1
        embed.set_footer(text=fmt("pagination.page_footer", page=new_page, max=max_pages))
        view = PaginationView(
            command="history",
            guild_id=interaction.guild.id if interaction.guild else 0,
            user_id=interaction.user.id,
            current_page=new_page,
            max_pages=max_pages,  # Dynamic max based on data
            params_hash=params_hash,
            callback_handler=lambda inter, pg: self._history_page_callback(
                inter, user, game_name, game_id, pg, days, params_hash, f_log
            )
        )
        # Chart file only on page 1, so we won't have it on other pages
        await interaction.response.edit_message(embed=embed, view=view)

    @command_root.command(name="settings", description=get("commands.settings.description"))
    @app_commands.describe(rated=get("commands.settings.param_rated"), private=get("commands.settings.param_private"))
    async def command_settings(self, ctx: discord.Interaction, rated: bool = None, private: bool = None):
        f_log = log.getChild("command.settings")
        f_log.debug(f"/settings called: rated={rated}, private={private} {contextify(ctx)}")

        id_matchmaking = {p.id: q for p, q in IN_MATCHMAKING.items()}
        if ctx.user.id not in id_matchmaking:
            await ctx.response.send_message(get("settings.not_in_matchmaking"),
                                            ephemeral=True)
            return

        matchmaker: MatchmakingInterface = id_matchmaking[ctx.user.id]
        if matchmaker.creator.id != ctx.user.id:
            await ctx.response.send_message(get("settings.only_creator"), ephemeral=True)
            return

        changes = []
        if rated is not None and rated != matchmaker.rated:
            if rated and getattr(matchmaker, "has_bots", False):
                await ctx.response.send_message(get("settings.rated_blocked_bots"), ephemeral=True)
                return
            matchmaker.rated = rated
            changes.append(fmt("settings.changed_rated", value=get("settings.yes") if rated else get("settings.no")))
        if private is not None and private != matchmaker.private:
            matchmaker.private = private
            changes.append(
                fmt("settings.changed_private", value=get("settings.yes") if private else get("settings.no")))

        if changes:
            await matchmaker.update_embed()
            await ctx.response.send_message(get("settings.updated") + "\n" + "\n".join(changes), ephemeral=True)
        else:
            await ctx.response.send_message(get("settings.no_changes"), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))
