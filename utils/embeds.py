import os

import discord

from api.Game import resolve_player_count
from configuration.constants import (
    EMBED_COLOR, ERROR_COLOR, SUCCESS_COLOR, WARNING_COLOR, 
    INFO_COLOR, GAME_COLOR, MATCHMAKING_COLOR
)
from utils.conversion import column_elo, column_names, column_turn, contextify
from utils.emojis import get_emoji_string
from utils.locale import get, fmt


class CustomEmbed(discord.Embed):
    """
    A modified version of discord.Embed with two key changes:

    * respects the default embed color of constants.py
    * Adds a bagel footer by default
    """

    def __init__(self, **kwargs):
        """
        Initialize the embed.
        :param kwargs: Arguments to the discord.Embed constructor
        """

        if 'color' not in kwargs:
            kwargs['color'] = EMBED_COLOR
        super().__init__(**kwargs)  # Force a consistent embed color based on the config

        self.set_footer(text=get("brand.footer"),
                        icon_url=get("brand.footer_icon"))


class SuccessEmbed(discord.Embed):
    """Embed for successful operations."""
    
    def __init__(self, title: str = None, description: str = None, **kwargs):
        kwargs['color'] = SUCCESS_COLOR
        kwargs['title'] = f"✅ {title or get('success.default_title')}"
        if description:
            kwargs['description'] = description
        super().__init__(**kwargs)
        self.set_footer(text=get("brand.name"))


class WarningEmbed(discord.Embed):
    """Embed for warnings and cautions."""
    
    def __init__(self, title: str = None, description: str = None, **kwargs):
        kwargs['color'] = WARNING_COLOR
        kwargs['title'] = f"⚠️ {title or get('warnings.default_title')}"
        if description:
            kwargs['description'] = description
        super().__init__(**kwargs)
        self.set_footer(text=get("brand.name"))


class UserErrorEmbed(discord.Embed):
    """
    Embed for user-facing errors with helpful guidance.
    Unlike ErrorEmbed, this is for expected user errors, not system errors.
    """
    
    def __init__(self, title: str = None, description: str = None, 
                 suggestion: str = None, **kwargs):
        kwargs['color'] = ERROR_COLOR
        kwargs['title'] = f"❌ {title or get('embeds.user_error.default_title')}"
        super().__init__(**kwargs)
        
        if description:
            self.description = description
        
        if suggestion:
            self.add_field(name=get("embeds.user_error.suggestion_field"), value=suggestion, inline=False)
        
        self.set_footer(text=get("embeds.user_error.footer"))


class LoadingEmbed(discord.Embed):
    """Embed to show while loading data."""
    
    def __init__(self, message: str = None, **kwargs):
        kwargs['color'] = INFO_COLOR
        kwargs['title'] = f"⏳ {message or get('loading.default')}"
        kwargs['description'] = get("loading.description")
        super().__init__(**kwargs)


class ErrorEmbed(discord.Embed):

    def __init__(self, ctx=None, what_failed=None, reason=None):
        current_directory = os.path.dirname(__file__).rstrip("utils")
        super().__init__(title=f"{get_emoji_string('facepalm')} {get('system_error.title')}",
                         color=ERROR_COLOR)
        self.add_field(name=f"{get_emoji_string('github')} {get('system_error.report_field')}",
                       value=fmt("system_error.report_value", github_issues_url=get("brand.github_url") + "/issues"))
        if ctx is not None:
            self.add_field(name=f"{get_emoji_string('clueless')} {get('system_error.context_field')}", 
                          value="```" + contextify(ctx) + "```",
                           inline=False)
        if what_failed is not None:
            self.add_field(name=f"{get_emoji_string('explosion')} {get('system_error.what_failed_field')}", 
                          value="```" + what_failed + "```",
                           inline=False)
        reason = reason.replace(current_directory, "")  # Remove the main part of the directory
        # (for obfuscation purposes)
        if reason is not None:
            text_fields = []
            running_total = 0
            temp_line = ""
            for line in reason.split("\n"):
                running_total += len(line) + 1
                if running_total <= 1017:  # = 1024 (field value limit) - 6 (backticks for proper formatting) - 1 (\n)
                    temp_line += line + "\n"
                else:
                    text_fields.append(temp_line + "\n")
                    temp_line = line
                    running_total = len(line) + 1
            text_fields.append(temp_line)

            for i in range(len(text_fields)):
                self.add_field(name=f"{get_emoji_string('hmm')} {fmt('system_error.reason_field', part=i+1, total=len(text_fields))}",
                               value="```" + text_fields[i] + "```",
                               inline=False)

        self.set_footer(text=get("system_error.footer"))


class GameOverviewEmbed(CustomEmbed):

    def __init__(self, game_name, game_type, rated, players, turn):
        title_key = "embeds.game_overview.title_rated" if rated else "embeds.game_overview.title_unrated"
        super().__init__(title=fmt(title_key, game_name=game_name),
                         description=get("embeds.game_overview.description"),
                         color=EMBED_COLOR)
        self.add_field(name=get("embeds.game_overview.field_players"), value=column_names(players), inline=True)
        self.add_field(name=get("embeds.game_overview.field_ratings"), value=column_elo(players, game_type), inline=True)
        self.add_field(name=get("embeds.game_overview.field_turn"), value=column_turn(players, turn), inline=True)


class GameOverEmbed(CustomEmbed):

    def __init__(self, rankings, game_name):
        super().__init__(title=fmt("embeds.game_over.title", game_name=game_name),
                         description=get("embeds.game_over.description"))
        self.add_field(name=get("embeds.game_over.field_rankings"), value=rankings, inline=True)


class InviteEmbed(CustomEmbed):
    def __init__(self, inviter, game_type, guild_name):
        super().__init__(
            title=get("embeds.invite.title"),
            description=fmt("embeds.invite.description", inviter=inviter.mention, game_type=game_type, guild_name=guild_name),
            color=EMBED_COLOR
        )
        self.add_field(name=get("embeds.invite.field_how_to_join"), 
                      value=get("embeds.invite.field_how_to_join_value"), inline=False)
        self.add_field(name=get("embeds.invite.field_note"), 
                      value=get("embeds.invite.field_note_value"), inline=False)


# ========== Interactive Help Embeds ==========

class HelpMainEmbed(CustomEmbed):
    """Main help embed with navigation to different help topics."""
    
    def __init__(self):
        name = get("brand.name")
        super().__init__(
            title=fmt("help.main.title", name=name),
            description=fmt("help.main.description", name=name),
            color=INFO_COLOR
        )
        self.add_field(
            name=get("help.main.fields.getting_started.name"),
            value=get("help.main.fields.getting_started.value"),
            inline=True
        )
        self.add_field(
            name=get("help.main.fields.game_list.name"),
            value=get("help.main.fields.game_list.value"),
            inline=True
        )
        self.add_field(
            name=get("help.main.fields.commands.name"),
            value=get("help.main.fields.commands.value"),
            inline=True
        )


class HelpGettingStartedEmbed(CustomEmbed):
    """Help embed for new users getting started."""
    
    def __init__(self):
        name = get("brand.name")
        super().__init__(
            title=fmt("help.getting_started.title", name=name),
            description=get("help.getting_started.description"),
            color=SUCCESS_COLOR
        )
        self.add_field(
            name=get("help.getting_started.fields.step1.name"),
            value=get("help.getting_started.fields.step1.value"),
            inline=False
        )
        self.add_field(
            name=get("help.getting_started.fields.step2.name"),
            value=get("help.getting_started.fields.step2.value"),
            inline=False
        )
        self.add_field(
            name=get("help.getting_started.fields.step3.name"),
            value=get("help.getting_started.fields.step3.value"),
            inline=False
        )
        self.add_field(
            name=get("help.getting_started.fields.tips.name"),
            value=get("help.getting_started.fields.tips.value"),
            inline=False
        )


class HelpCommandsEmbed(CustomEmbed):
    """Help embed showing all available commands."""
    
    def __init__(self):
        super().__init__(
            title=get("help.commands.title"),
            description=get("help.commands.description"),
            color=INFO_COLOR
        )
        self.add_field(
            name=get("help.commands.fields.playing.name"),
            value=get("help.commands.fields.playing.value"),
            inline=False
        )
        self.add_field(
            name=get("help.commands.fields.stats.name"),
            value=get("help.commands.fields.stats.value"),
            inline=False
        )
        self.add_field(
            name=get("help.commands.fields.info.name"),
            value=get("help.commands.fields.info.value"),
            inline=False
        )


class HelpGameInfoEmbed(CustomEmbed):
    """Help embed showing detailed information about a specific game."""
    
    def __init__(self, game_id: str, game_class):
        game_name = getattr(game_class, 'name', game_id)
        description = getattr(game_class, 'description', get("help.game_info.no_description"))
        players = resolve_player_count(game_class)
        if players is None:
            players = get("help.game_info.unknown")
        time_est = getattr(game_class, 'time', get("help.game_info.unknown"))
        difficulty = getattr(game_class, 'difficulty', get("help.game_info.unknown"))
        author = getattr(game_class, 'author', get("help.game_info.unknown"))
        
        if isinstance(players, list):
            player_text = fmt("help.game_info.players_range_format", min=min(players), max=max(players))
        else:
            player_text = fmt("help.game_info.players_format", count=players)
        
        super().__init__(
            title=fmt("help.game_info.title", game_name=game_name),
            description=description,
            color=GAME_COLOR
        )
        self.add_field(name=get("help.game_info.field_players"), value=player_text, inline=True)
        self.add_field(name=get("help.game_info.field_duration"), value=time_est, inline=True)
        self.add_field(name=get("help.game_info.field_difficulty"), value=difficulty, inline=True)
        self.add_field(
            name=get("help.game_info.field_quick_start"),
            value=fmt("help.game_info.field_quick_start_value", game_id=game_id),
            inline=False
        )
        self.add_field(name=get("help.game_info.field_author"), value=author, inline=True)
        self.add_field(
            name=get("help.game_info.field_learn_more"),
            value=fmt("help.game_info.field_learn_more_value", game_id=game_id),
            inline=False,
        )


class MatchmakingEmbed(CustomEmbed):
    """Enhanced matchmaking lobby embed with clear information."""
    
    def __init__(self, game_name: str, game_id: str, creator, players: list, 
                 min_players: int, max_players: int, rated: bool = True, private: bool = False):
        status = get("embeds.matchmaking.status_private") if private else get("embeds.matchmaking.status_public")
        rating_status = get("embeds.matchmaking.rated") if rated else get("embeds.matchmaking.unrated")
        
        super().__init__(
            title=fmt("embeds.matchmaking.title", game_name=game_name),
            description=fmt("embeds.matchmaking.description", creator=creator.display_name),
            color=MATCHMAKING_COLOR
        )
        
        # Player list
        if players:
            player_list = "\n".join([
                f"• {getattr(p, 'display_name', None) or getattr(p, 'name', str(p))}"
                for p in players
            ])
        else:
            player_list = get("embeds.matchmaking.no_players")
        
        self.add_field(
            name=fmt("embeds.matchmaking.field_players", current=len(players), max=max_players),
            value=player_list,
            inline=True
        )
        self.add_field(
            name=get("embeds.matchmaking.field_game_info"),
            value=fmt("embeds.matchmaking.game_info_value", 
                     status=status, rating_status=rating_status, 
                     min=min_players, max=max_players),
            inline=True
        )
        
        if len(players) >= min_players:
            self.add_field(
                name=get("embeds.matchmaking.field_ready"),
                value=get("embeds.matchmaking.ready_value"),
                inline=False
            )
        else:
            needed = min_players - len(players)
            plural_s = "s" if needed > 1 else ""
            self.add_field(
                name=fmt("embeds.matchmaking.field_waiting", needed=needed, s=plural_s),
                value=get("embeds.matchmaking.waiting_value"),
                inline=False
            )


class FirstTimeUserEmbed(CustomEmbed):
    """Welcome embed for first-time users with tutorial guidance."""
    
    def __init__(self, game_name: str = None):
        name = get("brand.name")
        super().__init__(
            title=fmt("tutorial.title", name=name),
            description=get("tutorial.description"),
            color=SUCCESS_COLOR
        )
        
        self.add_field(
            name=get("tutorial.fields.how_games_work.name"),
            value=get("tutorial.fields.how_games_work.value"),
            inline=False
        )
        
        self.add_field(
            name=get("tutorial.fields.ratings.name"),
            value=get("tutorial.fields.ratings.value"),
            inline=False
        )
        
        self.add_field(
            name=get("tutorial.fields.tips.name"),
            value=get("tutorial.fields.tips.value"),
            inline=False
        )
        
        if game_name:
            self.add_field(
                name=fmt("tutorial.fields.ready_to_play.name", game_name=game_name),
                value=get("tutorial.fields.ready_to_play.value"),
                inline=False
            )
