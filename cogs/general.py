import hashlib
import importlib
import logging
from datetime import datetime

from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from configuration.constants import *
from utils import database as db, ramcheck
from utils.conversion import contextify
from utils.embeds import CustomEmbed, InviteEmbed
from utils.emojis import get_emoji_string
from utils.graphs import generate_elo_chart
from utils.interfaces import MatchmakingInterface, user_in_active_game
from utils.views import InviteView, PaginationView

log = logging.getLogger(LOGGING_ROOT)


def _pluralize(count: int, singular: str, plural: str = None) -> str:
    return singular if count == 1 else (plural or singular + "s")


def _ordinal(value: int) -> str:
    if value is None:
        return "?"
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def _build_ascii_sparkline(values, width: int = 24) -> str:
    if not values:
        return "no-data"
    if len(values) > width:
        step = (len(values) - 1) / (width - 1)
        sampled = [values[round(i * step)] for i in range(width)]
    else:
        sampled = values

    minimum = min(sampled)
    maximum = max(sampled)
    if maximum == minimum:
        return "=" * len(sampled)

    levels = "._-:=+*#%@"
    span = maximum - minimum
    chars = []
    for value in sampled:
        idx = int((value - minimum) / span * (len(levels) - 1))
        chars.append(levels[idx])
    return "".join(chars)


async def autocomplete_game_id(ctx: discord.Interaction, current: str) -> list[Choice[str]]:
    query = current.lower().strip()
    matches = []

    for game_id, (module_name, class_name) in GAME_TYPES.items():
        game_class = getattr(importlib.import_module(module_name), class_name)
        display_name = getattr(game_class, "name", game_id)

        searchable = f"{game_id} {display_name}".lower()
        if query and query not in searchable:
            continue

        if query and game_id.lower().startswith(query):
            rank = 0
        elif query and display_name.lower().startswith(query):
            rank = 1
        else:
            rank = 2
        matches.append((rank, game_id.lower(), game_id, game_id))

    matches.sort(key=lambda item: (item[0], item[1]))
    return [Choice(name=name[:100], value=value) for _, _, name, value in matches[:25]]


class GeneralCog(commands.Cog):
    def __init__(self, bot: discord.Client):
        self.bot = bot

    command_root = app_commands.Group(name=LOGGING_ROOT, description="Everything that isn't a game.", guild_only=False)

    @command_root.command(name="invite",
                          description="Invite a player to play a game, or remove them from the blacklist in public games.")
    @app_commands.describe(game="The game to start if you aren't already in one")
    @app_commands.autocomplete(game=autocomplete_game_id)
    async def command_invite(self, ctx: discord.Interaction,
                             user: discord.User,
                             game: str = None,
                             user2: discord.User = None,
                             user3: discord.User = None,
                             user4: discord.User = None,
                             user5: discord.User = None) -> None:
        f_log = log.getChild("command.invite")
        f_log.debug(f"/invite called: {contextify(ctx)}")
        invited_users = {user, user2, user3, user4, user5}
        if None in invited_users:
            invited_users.remove(None)

        id_matchmaking = {p.id: q for p, q in IN_MATCHMAKING.items()}

        if ctx.user.id not in id_matchmaking:
            if user_in_active_game(ctx.user.id):
                await ctx.response.send_message(
                    "You are already in an active game in another server. Finish that game before starting a new one.",
                    ephemeral=True
                )
                return

            if game is None:
                await ctx.response.send_message("You aren't in matchmaking. Please specify a `game` to start one!",
                                                ephemeral=True)
                return

            if game not in GAME_TYPES:
                await ctx.response.send_message(
                    f"Unknown game: {game}. Use `/playcord catalog` to see available games.", ephemeral=True)
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

        if matchmaker.private and matchmaker.creator.id != ctx.user.id:
            await ctx.response.send_message("You aren't the creator of this game, so you can't invite people to play.",
                                            ephemeral=True)
            f_log.debug(f"/invite rejected: not creator. {contextify(ctx)}")
            return

        game_type = matchmaker.game.name
        failed_invites = {}
        for invited_user in filter(None, invited_users):
            if invited_user not in matchmaker.message.guild.members:
                failed_invites[invited_user] = "Member was not in server that the game was"
                continue
            if invited_user.id in [p.id for p in matchmaker.queued_players]:
                failed_invites[invited_user] = "Member was already in matchmaking."
                continue
            if user_in_active_game(invited_user.id):
                failed_invites[invited_user] = "Member was already in a game."
                continue
            if invited_user.bot:
                failed_invites[invited_user] = "Member was a bot :skull:."
                continue

            # Invitation
            embed = InviteEmbed(inviter=ctx.user, game_type=game_type, guild_name=matchmaker.message.guild.name)

            await invited_user.send(embed=embed,
                                    view=InviteView(join_button_id=BUTTON_PREFIX_INVITE + str(matchmaker.message.id),
                                                    game_link=matchmaker.message.jump_url))
            continue

        if not len(failed_invites):
            f_log.debug(f"/invite success: {len(invited_users)} succeeded, 0 failed. {contextify(ctx)}")
            if ctx.response.is_done():
                await ctx.followup.send("Invites sent successfully.", ephemeral=True)
            else:
                await ctx.response.send_message("Invites sent successfully.", ephemeral=True)
            return
        elif len(failed_invites) == len(invited_users):
            message = "Failed to send any invites. Errors:"
        else:
            message = "Failed to send invites to the following users:"
        f_log.debug(f"/invite partial or no success: {len(invited_users) - len(failed_invites)} succeeded,"
                    f" {len(failed_invites)} failed. {contextify(ctx)}")
        final = message + "\n"
        for fail in failed_invites:
            final += f"{fail.mention} - {failed_invites[fail]}\n"

        if ctx.response.is_done():
            await ctx.followup.send(final, ephemeral=True)
        else:
            await ctx.response.send_message(final, ephemeral=True)

    @command_root.command(name="kick", description="Remove a user from your lobby without banning them.")
    async def command_kick(self, ctx: discord.Interaction, user: discord.User, reason: str = None):
        f_log = log.getChild("command.kick")
        id_matchmaking = {p.id: q for p, q in IN_MATCHMAKING.items()}

        if ctx.user.id not in id_matchmaking:
            await ctx.response.send_message("You aren't in matchmaking, so you can't kick anyone.",
                                            ephemeral=True)
            return
        matchmaker: MatchmakingInterface = id_matchmaking[ctx.user.id]
        if matchmaker.creator.id != ctx.user.id:
            await ctx.response.send_message(
                "You aren't the creator of this game, so you can't kick people from the game.",
                ephemeral=True)
            return

        return_value = await matchmaker.kick(user, reason)
        await ctx.response.send_message(return_value, ephemeral=True)

    @command_root.command(name="ban",
                          description="Remove a user from whitelist (private games) or blacklist them (public games).")
    async def command_ban(self, ctx: discord.Interaction, user: discord.User, reason: str = None):
        f_log = log.getChild("command.ban")
        id_matchmaking = {p.id: q for p, q in IN_MATCHMAKING.items()}

        if ctx.user.id not in id_matchmaking:
            await ctx.response.send_message("You aren't in matchmaking, so you can't ban anyone.",
                                            ephemeral=True)
            return
        matchmaker: MatchmakingInterface = id_matchmaking[ctx.user.id]
        if matchmaker.creator.id != ctx.user.id:
            await ctx.response.send_message(
                "You aren't the creator of this game, so you can't ban people from the game.",
                ephemeral=True)
            return

        return_value = await matchmaker.ban(user, reason)
        await ctx.response.send_message(return_value, ephemeral=True)

    @command_root.command(name="stats", description="Get stats about the bot")
    async def command_stats(self, ctx: discord.Interaction):
        f_log = log.getChild("command.stats")
        f_log.debug(f"/stats called: {contextify(ctx)}")

        server_count = len(self.bot.guilds)
        member_count = len(set(self.bot.get_all_members()))

        shard_id = ctx.guild.shard_id
        shard_ping = self.bot.latency
        shard_servers = len([guild for guild in self.bot.guilds if guild.shard_id == shard_id])

        embed = CustomEmbed(title=f'PlayCord Stats {get_emoji_string("pointing")}',
                            description=f"This instance of PlayCord is managed by **{MANAGED_BY}**", color=INFO_COLOR)

        embed.add_field(name='💻 Bot version:', value=VERSION)
        embed.add_field(name='🐍 discord.py version:', value=discord.__version__)
        embed.add_field(name='👾 Games loaded:', value=len(GAME_TYPES))
        embed.add_field(name='🏘️ Total servers:', value=server_count)
        embed.add_field(name="💪 Total number of owners:", value=len(OWNERS))
        embed.add_field(name="💾 Used RAM (this shard)", value=ramcheck.get_ram_usage_mb())
        embed.add_field(name='#️⃣ Shard ID:', value=shard_id)
        embed.add_field(name='🛜 Shard ping:', value=str(round(shard_ping * 100, 2)) + " ms")
        embed.add_field(name='🏘️️ Shard servers:', value=shard_servers)
        embed.add_field(name=f'{get_emoji_string("user")} Users:', value=member_count)
        embed.add_field(name="⏰ Users in matchmaking:", value=len(IN_MATCHMAKING))
        embed.add_field(name="🎮 Users in game:", value=len(IN_GAME))

        await ctx.response.send_message(embed=embed)

    @command_root.command(name="about", description="About the bot")
    async def command_about(self, ctx: discord.Interaction):
        f_log = log.getChild("command.about")
        libraries = ["discord.py", "svg.py", "ruamel.yaml", "cairosvg", "trueskill", "mpmath"]
        f_log.debug(f"/about called: {contextify(ctx)}")

        embed = CustomEmbed(title='About PlayCord 🎲', color=INFO_COLOR)
        embed.add_field(name="Bot by:", value="[@quantumbagel](https://github.com/quantumbagel)")
        embed.add_field(name="Source code:", value="[here](https://github.com/PlayCord/bot)")
        embed.add_field(name="PFP/Banner:", value="[@soldship](https://github.com/quantumsoldship)")
        embed.add_field(name="Inspiration:",
                        value="[LoRiggio (Liar's Dice Bot)](https://github.com/Pixelz22/LoRiggioDev) by [@Pixelz22](https://github.com/Pixelz22)",
                        inline=True)
        embed.add_field(name="Libraries used:",
                        value="\n".join([f"[{lib}](https://pypi.org/project/{lib})" for lib in libraries]),
                        inline=False)
        embed.add_field(name="Development time:", value="October 2024 - March 2025\nMarch 2026 - Present")
        embed.set_footer(text="© 2026 Julian Reder. All rights reserved.")

        await ctx.response.send_message(embed=embed)

    @command_root.command(name="help", description="Get help on how to use the bot")
    async def command_help(self, ctx: discord.Interaction):
        f_log = log.getChild("command.help")
        f_log.debug(f"/help called: {contextify(ctx)}")

        embed = CustomEmbed(title=f"{NAME} Help 📚", color=INFO_COLOR)
        embed.description = f"Welcome to {NAME}! Here's how to get started."
        embed.add_field(name="🎮 Starting a Game",
                        value="Use `/play <game>` to start a game. For example: `/play tictactoe`", inline=False)
        embed.add_field(name="👥 Joining Games",
                        value="Click the **Join** button on any matchmaking message to join a game.", inline=False)
        embed.add_field(name="📊 Leaderboards",
                        value="Use `/playcord leaderboard <game>` to see the top players for a game.", inline=False)
        embed.add_field(name="📖 Game Catalog", value="Use `/playcord catalog` to see all available games.",
                        inline=False)
        embed.add_field(name="👤 Your Profile",
                        value="Use `/playcord profile` to see your stats, or `/playcord profile @user` to see someone else's.",
                        inline=False)
        embed.add_field(name="⚙️ Commands",
                        value="`/playcord stats` - Bot statistics\n`/playcord about` - About the bot\n`/playcord invite @user` - Invite a user to your game\n`/playcord kick @user` - Kick a user from your lobby\n`/playcord ban @user` - Ban a user from your lobby",
                        inline=False)
        embed.add_field(name="🔗 Links",
                        value="[GitHub](https://github.com/PlayCord/bot) | [README](https://github.com/PlayCord/bot/blob/master/README.md)",
                        inline=False)

        await ctx.response.send_message(embed=embed)

    @command_root.command(name="leaderboard", description="View the leaderboard for a game")
    @app_commands.describe(game="The game to view the leaderboard for",
                           scope="Whether to show server or global leaderboard", page="Page number of the leaderboard")
    @app_commands.choices(scope=[Choice(name="Server", value="server"), Choice(name="Global", value="global")])
    @app_commands.autocomplete(game=autocomplete_game_id)
    async def command_leaderboard(self, ctx: discord.Interaction, game: str, scope: str = "server", page: int = 1):
        f_log = log.getChild("command.leaderboard")
        f_log.debug(f"/leaderboard called for game={game}, scope={scope}, page={page}: {contextify(ctx)}")

        if game not in GAME_TYPES:
            await ctx.response.send_message(
                f"Unknown game type: {game}. Use `/playcord catalog` to see available games.", ephemeral=True)
            return

        game_class = getattr(importlib.import_module(GAME_TYPES[game][0]), GAME_TYPES[game][1])
        game_name = game_class.name
        game_db = db.database.get_game(game)
        if not game_db:
            await ctx.response.send_message("This game is not registered in the database yet.", ephemeral=True)
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
        embed.set_footer(text=f"Page {page}/{max_pages}")

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
        await ctx.response.send_message(embed=embed, view=view)

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
            scope_text = "Global leaderboard"
        else:
            # Fetch one extra item to check if there are more pages
            leaderboard_data = db.database.get_leaderboard(
                guild.id,
                game_id,
                limit=limit + 1,
                offset=offset,
                min_matches=1,
            )
            scope_text = f"Server leaderboard for {guild.name}"

        embed = CustomEmbed(title=f"🏆 {game_name} Leaderboard", color=INFO_COLOR)
        embed.description = scope_text

        has_data = bool(leaderboard_data)
        # If we got more than limit items, there are more pages
        is_last_page = len(leaderboard_data) <= limit

        # Only use the first 'limit' items for display
        display_data = leaderboard_data[:limit]

        if not display_data:
            embed.add_field(name="No Data",
                            value="No players have played this game yet!" if page == 1 else "No more players to display.",
                            inline=False)
        else:
            rankings = []
            for i, entry in enumerate(display_data, start=offset + 1):
                user_id = entry['user_id']
                conservative = entry.get('conservative_rating', entry.get('mu', 0))
                mu = entry.get('mu', 0)
                matches = entry.get('matches_played', 0)
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"#{i}"
                rankings.append(
                    f"{medal} <@{user_id}> - **{round(conservative)}** CR "
                    f"(mu {round(mu)}, {matches} {_pluralize(matches, 'game')})"
                )
            embed.add_field(name="Rankings", value="\n".join(rankings), inline=False)

        return embed, has_data, is_last_page

    async def _leaderboard_page_callback(self, interaction: discord.Interaction, game: str, game_name: str,
                                         game_id: int, scope: str, new_page: int,
                                         limit: int, params_hash: str):
        """Callback for leaderboard pagination buttons."""
        embed, has_data, is_last_page = self._build_leaderboard_embed(game, game_name, game_id, scope,
                                                                      interaction.guild,
                                                                      new_page, limit)
        max_pages = new_page if is_last_page else new_page + 1
        embed.set_footer(text=f"Page {new_page}/{max_pages}")
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

    @command_root.command(name="catalog", description="View all available games")
    @app_commands.describe(page="Page number of the catalog")
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

        embed = CustomEmbed(title=f"🎲 {NAME} Game Catalog", color=INFO_COLOR)
        embed.description = f"Browse all available games. Use `/play <game>` to start playing!"

        for game_id in page_games:
            game_info = GAME_TYPES[game_id]
            game_class = getattr(importlib.import_module(game_info[0]), game_info[1])
            game_name = getattr(game_class, 'name', game_id)
            game_desc = getattr(game_class, 'description', 'No description available.')
            game_time = getattr(game_class, 'time', 'Unknown')
            game_difficulty = getattr(game_class, 'difficulty', 'Unknown')
            game_players = getattr(game_class, 'players', 'Unknown')
            player_text = f"{min(game_players)}-{max(game_players)} players" if isinstance(game_players,
                                                                                           list) else f"{game_players} players"

            embed.add_field(name=f"🎮 {game_name}", value=(
                f"{game_desc[:100]}{'...' if len(game_desc) > 100 else ''}\n⏰ {game_time} | 👤 {player_text} | 📈 {game_difficulty}\n**Command:** `/play {game_id}`"),
                            inline=False)

        embed.set_footer(text=f"Page {page}/{total_pages}")
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

    @command_root.command(name="profile", description="View a player's profile and stats")
    @app_commands.describe(user="The user to view (defaults to yourself)")
    async def command_profile(self, ctx: discord.Interaction, user: discord.User = None):
        f_log = log.getChild("command.profile")
        if user is None: user = ctx.user
        f_log.debug(f"/profile called for user={user.id}: {contextify(ctx)}")

        player = db.database.get_player(user, ctx.guild.id)
        if player is None:
            await ctx.response.send_message("Couldn't retrieve player data.", ephemeral=True)
            return

        embed = CustomEmbed(title=f"👤 {user.display_name}'s Profile", color=INFO_COLOR)
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
                        rank_badge = "🏆" if global_rank == 1 else "🥇" if global_rank <= 3 else "⭐" if global_rank <= 10 else ""
                        game_stats.append(
                            f"**{game_name}**: {round(mu)} ({matches} {_pluralize(matches, 'game')}) {rank_badge} #{global_rank} Global")
                    else:
                        game_stats.append(f"**{game_name}**: {round(mu)} ({matches} {_pluralize(matches, 'game')})")
                else:
                    game_stats.append(f"**{game_name}**: {round(mu)} ({matches} {_pluralize(matches, 'game')})")

        if game_stats:
            embed.add_field(name="📊 Game Ratings", value="\n".join(game_stats), inline=False)
        else:
            embed.add_field(name="📊 Game Ratings", value="No games played yet!", inline=False)

        match_history = db.database.get_user_match_history(user.id, ctx.guild.id, limit=5)
        if match_history:
            history_lines = [
                f"**{m.get('game_name', 'Unknown')}** - {_ordinal(m.get('final_ranking'))}"
                f"/{m.get('player_count', '?')} | seat #{m.get('player_number', '?')}"
                f" | {'rated' if m.get('is_rated', True) else 'casual'}"
                f" | ({'+' if m.get('mu_delta', 0) >= 0 else ''}{round(m.get('mu_delta', 0))})"
                for m in match_history]
            embed.add_field(name="📜 Recent Matches", value="\n".join(history_lines), inline=False)
        else:
            embed.add_field(name="📜 Recent Matches", value="No recent matches.", inline=False)

        total_matches = db.database.count_matches_for_user(user.id, ctx.guild.id)
        embed.add_field(
            name="🎮 Total Games Played",
            value=f"{total_matches} {_pluralize(total_matches, 'game')}",
            inline=True,
        )
        await ctx.response.send_message(embed=embed)

    @command_root.command(name="history", description="View a player's per-game match history and rating trend.")
    @app_commands.describe(
        game="Game to inspect",
        user="The user to view (defaults to yourself)",
        page="Page number for match history",
        days="Days included in trend graph (1-365)",
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
                f"Unknown game type: {game}. Use `/playcord catalog` to see available games.",
                ephemeral=True,
            )
            return

        game_db = db.database.get_game(game)
        if not game_db:
            await ctx.response.send_message("This game is not registered in the database yet.", ephemeral=True)
            return

        game_class = getattr(importlib.import_module(GAME_TYPES[game][0]), GAME_TYPES[game][1])
        game_name = getattr(game_class, 'name', game)

        embed, chart_file, has_data, is_last_page = self._build_history_embed(
            user, game_name, game_db.game_id, ctx.guild.id, page, days, f_log
        )

        max_pages = page if is_last_page else page + 1
        embed.set_footer(text=f"Page {page}/{max_pages}")
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

        embed = CustomEmbed(title=f"📈 {user.display_name} - {game_name} history", color=INFO_COLOR)
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
                    f"{rank_text}/{row.get('player_count', '?')} | seat #{row.get('player_number', '?')}"
                    f" | {'rated' if row.get('is_rated', True) else 'casual'}"
                    f" | {'+' if delta >= 0 else ''}{round(delta)}"
                )
            embed.add_field(name="Recent matches", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="Recent matches",
                            value="No completed matches found." if page == 1 else "No more matches to display.",
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
                    title=f"{user.display_name}'s {game_name} Rating",
                    figsize=(10, 6),
                    dpi=100
                )
                chart_file = discord.File(chart_buffer, filename="rating_chart.png")
                embed.set_image(url="attachment://rating_chart.png")

                delta_total = points[-1] - points[0]
                embed.add_field(
                    name=f"Rating trend ({days}d)",
                    value=(
                        f"Start: {round(points[0])} → End: {round(points[-1])} "
                        f"({'+' if delta_total >= 0 else ''}{round(delta_total)})"
                    ),
                    inline=False,
                )
            except Exception as e:
                f_log.error(f"Failed to generate chart: {e}")
                delta_total = points[-1] - points[0]
                embed.add_field(
                    name=f"Rating trend ({days}d)",
                    value=(
                        f"Start: {round(points[0])} → End: {round(points[-1])} "
                        f"({'+' if delta_total >= 0 else ''}{round(delta_total)})"
                    ),
                    inline=False,
                )
        elif page == 1:
            embed.add_field(name=f"Rating trend ({days}d)", value="No rating history for this period.", inline=False)

        return embed, chart_file, has_data, is_last_page

    async def _history_page_callback(self, interaction: discord.Interaction, user, game_name: str,
                                     game_id: int, new_page: int, days: int, params_hash: str, f_log):
        """Callback for history pagination buttons."""
        embed, chart_file, has_data, is_last_page = self._build_history_embed(
            user, game_name, game_id, interaction.guild.id, new_page, days, f_log
        )
        max_pages = new_page if is_last_page else new_page + 1
        embed.set_footer(text=f"Page {new_page}/{max_pages}")
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

    @command_root.command(name="settings", description="Change settings for your current game lobby")
    @app_commands.describe(rated="Whether the game should be rated", private="Whether the game should be private")
    async def command_settings(self, ctx: discord.Interaction, rated: bool = None, private: bool = None):
        f_log = log.getChild("command.settings")
        f_log.debug(f"/settings called: rated={rated}, private={private} {contextify(ctx)}")

        id_matchmaking = {p.id: q for p, q in IN_MATCHMAKING.items()}
        if ctx.user.id not in id_matchmaking:
            await ctx.response.send_message("You aren't in matchmaking. Start a game first with `/play <game>`.",
                                            ephemeral=True)
            return

        matchmaker: MatchmakingInterface = id_matchmaking[ctx.user.id]
        if matchmaker.creator.id != ctx.user.id:
            await ctx.response.send_message("Only the game creator can change settings.", ephemeral=True)
            return

        changes = []
        if rated is not None and rated != matchmaker.rated:
            matchmaker.rated = rated
            changes.append(f"Rated: {'Yes' if rated else 'No'}")
        if private is not None and private != matchmaker.private:
            matchmaker.private = private
            changes.append(f"Private: {'Yes' if private else 'No'}")

        if changes:
            await matchmaker.update_embed()
            await ctx.response.send_message(f"Settings updated:\n" + "\n".join(changes), ephemeral=True)
        else:
            await ctx.response.send_message("No settings were changed.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))
