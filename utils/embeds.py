import os

import discord

from configuration.constants import (
    EMBED_COLOR, ERROR_COLOR, SUCCESS_COLOR, WARNING_COLOR, 
    INFO_COLOR, GAME_COLOR, MATCHMAKING_COLOR, NAME
)
from utils.conversion import column_elo, column_names, column_turn, contextify
from utils.emojis import get_emoji_string


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

        self.set_footer(text=f"Made with ❤ by @quantumbagel",
                        # Force bagel footer by default, this can be overriden tho
                        icon_url="https://avatars.githubusercontent.com/u/58365715")


class SuccessEmbed(discord.Embed):
    """Embed for successful operations."""
    
    def __init__(self, title: str = "Success!", description: str = None, **kwargs):
        kwargs['color'] = SUCCESS_COLOR
        kwargs['title'] = f"✅ {title}"
        if description:
            kwargs['description'] = description
        super().__init__(**kwargs)
        self.set_footer(text=f"{NAME}")


class WarningEmbed(discord.Embed):
    """Embed for warnings and cautions."""
    
    def __init__(self, title: str = "Warning", description: str = None, **kwargs):
        kwargs['color'] = WARNING_COLOR
        kwargs['title'] = f"⚠️ {title}"
        if description:
            kwargs['description'] = description
        super().__init__(**kwargs)
        self.set_footer(text=f"{NAME}")


class UserErrorEmbed(discord.Embed):
    """
    Embed for user-facing errors with helpful guidance.
    Unlike ErrorEmbed, this is for expected user errors, not system errors.
    """
    
    def __init__(self, title: str = "Oops!", description: str = None, 
                 suggestion: str = None, **kwargs):
        kwargs['color'] = ERROR_COLOR
        kwargs['title'] = f"❌ {title}"
        super().__init__(**kwargs)
        
        if description:
            self.description = description
        
        if suggestion:
            self.add_field(name="💡 Suggestion", value=suggestion, inline=False)
        
        self.set_footer(text=f"Need help? Use /playcord help")


class LoadingEmbed(discord.Embed):
    """Embed to show while loading data."""
    
    def __init__(self, message: str = "Loading...", **kwargs):
        kwargs['color'] = INFO_COLOR
        kwargs['title'] = f"⏳ {message}"
        kwargs['description'] = "Please wait while we fetch your data..."
        super().__init__(**kwargs)


class ErrorEmbed(discord.Embed):

    def __init__(self, ctx=None, what_failed=None, reason=None):
        current_directory = os.path.dirname(__file__).rstrip("utils")
        super().__init__(title=f"{get_emoji_string("facepalm")} Something went wrong!",
                         color=ERROR_COLOR)  # Force a consistent embed color based on the config
        self.add_field(name=f"{get_emoji_string("github")} Please report the issue on GitHub",
                       value="I would really appreciate if you reported this error (and a detailed description of what you did to cause it if possible) on the [GitHub issue tracker](https://github.com/PlayCord/bot/issues)")
        if ctx is not None:
            self.add_field(name=f"{get_emoji_string("clueless")} Context:", value="```" + contextify(ctx) + "```",
                           inline=False)
        if what_failed is not None:
            self.add_field(name=f"{get_emoji_string("explosion")} What failed?", value="```" + what_failed + "```",
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
                self.add_field(name=f"{get_emoji_string("hmm")} Reason (part {i + 1} of {len(text_fields)}):",
                               value="```" + text_fields[i] + "```",
                               inline=False)

        self.set_footer(text=f"Sorry for the inconvenience! Please report this issue on our GitHub page.")


class GameOverviewEmbed(CustomEmbed):

    def __init__(self, game_name, game_type, rated, players, turn):
        rated_text = "Rated" if rated else "Unrated"
        super().__init__(title=f"{rated_text} {game_name} game started!",
                         description="Click the button if you want to spectate the game, or just view the game's progress.",
                         color=EMBED_COLOR)  # Force a consistent embed color based on the config
        self.add_field(name="Players:", value=column_names(players), inline=True)
        self.add_field(name="Ratings:", value=column_elo(players, game_type), inline=True)
        self.add_field(name="Turn:", value=column_turn(players, turn), inline=True)


class GameOverEmbed(CustomEmbed):

    def __init__(self, rankings, game_name):
        super().__init__(title=f"{game_name} game over!",
                         description=f"Thanks so much for playing! Here are the rankings:")
        self.add_field(name="Rankings:", value=rankings, inline=True)


class InviteEmbed(CustomEmbed):
    def __init__(self, inviter, game_type, guild_name):
        super().__init__(
            title=f"👋 You've been invited!",
            description=f"{inviter.mention} has invited you to play a game of **{game_type}** in **{guild_name}**.",
            color=EMBED_COLOR
        )
        self.add_field(name="How to join?", value="Click the 'Join Game' button below to join the lobby.", inline=False)
        self.add_field(name="Note:", value="If you don't want to play, you can simply ignore this message.",
                       inline=False)


# ========== Interactive Help Embeds ==========

class HelpMainEmbed(CustomEmbed):
    """Main help embed with navigation to different help topics."""
    
    def __init__(self):
        super().__init__(
            title=f"📚 {NAME} Help Center",
            description=(
                f"Welcome to **{NAME}**! I'm your friendly game bot for Discord.\n\n"
                "Use the buttons below to explore different topics, or try these quick commands:\n"
                "• `/play <game>` - Start a new game\n"
                "• `/playcord catalog` - Browse all games\n"
                "• `/playcord profile` - View your stats"
            ),
            color=INFO_COLOR
        )
        self.add_field(
            name="🎮 Getting Started",
            value="New here? Click **Getting Started** below!",
            inline=True
        )
        self.add_field(
            name="📖 Game List",
            value="See all available games",
            inline=True
        )
        self.add_field(
            name="⚙️ Commands",
            value="Full command reference",
            inline=True
        )


class HelpGettingStartedEmbed(CustomEmbed):
    """Help embed for new users getting started."""
    
    def __init__(self):
        super().__init__(
            title="🎮 Getting Started with PlayCord",
            description="Let's get you playing in under a minute!",
            color=SUCCESS_COLOR
        )
        self.add_field(
            name="Step 1: Start a Game",
            value=(
                "Use `/play <game>` to create a new game lobby.\n"
                "**Example:** `/play tictactoe`\n\n"
                "Not sure which game? Try `/playcord catalog` to browse!"
            ),
            inline=False
        )
        self.add_field(
            name="Step 2: Invite Friends (Optional)",
            value=(
                "Your lobby is open to anyone by default.\n"
                "• **Public game:** Anyone can click Join\n"
                "• **Invite players:** Use `/playcord invite @user`"
            ),
            inline=False
        )
        self.add_field(
            name="Step 3: Play!",
            value=(
                "Once enough players join, click **Start** to begin.\n"
                "Follow the on-screen instructions to make your moves!"
            ),
            inline=False
        )
        self.add_field(
            name="💡 Pro Tips",
            value=(
                "• Games track your rating - compete for the leaderboard!\n"
                "• Use `/playcord profile` to see your stats\n"
                "• Click buttons instead of typing when available"
            ),
            inline=False
        )


class HelpCommandsEmbed(CustomEmbed):
    """Help embed showing all available commands."""
    
    def __init__(self):
        super().__init__(
            title="⚙️ Command Reference",
            description="Here are all the commands you can use:",
            color=INFO_COLOR
        )
        self.add_field(
            name="🎮 Playing Games",
            value=(
                "`/play <game>` - Start a new game\n"
                "`/playcord catalog` - Browse all games\n"
                "`/playcord invite @user` - Invite to your lobby\n"
                "`/playcord kick @user` - Remove from lobby\n"
                "`/playcord ban @user` - Ban from lobby"
            ),
            inline=False
        )
        self.add_field(
            name="📊 Stats & Rankings",
            value=(
                "`/playcord profile [@user]` - View player stats\n"
                "`/playcord leaderboard <game>` - Top players\n"
                "`/playcord history` - Your recent matches"
            ),
            inline=False
        )
        self.add_field(
            name="ℹ️ Information",
            value=(
                "`/playcord help` - This help menu\n"
                "`/playcord about` - About the bot\n"
                "`/playcord stats` - Bot statistics"
            ),
            inline=False
        )


class HelpGameInfoEmbed(CustomEmbed):
    """Help embed showing detailed information about a specific game."""
    
    def __init__(self, game_id: str, game_class):
        game_name = getattr(game_class, 'name', game_id)
        description = getattr(game_class, 'description', 'No description available.')
        players = getattr(game_class, 'players', 'Unknown')
        time_est = getattr(game_class, 'time', 'Unknown')
        difficulty = getattr(game_class, 'difficulty', 'Unknown')
        author = getattr(game_class, 'author', 'Unknown')
        
        if isinstance(players, list):
            player_text = f"{min(players)}-{max(players)} players"
        else:
            player_text = f"{players} players"
        
        super().__init__(
            title=f"🎮 How to Play: {game_name}",
            description=description,
            color=GAME_COLOR
        )
        self.add_field(name="👥 Players", value=player_text, inline=True)
        self.add_field(name="⏰ Duration", value=time_est, inline=True)
        self.add_field(name="📈 Difficulty", value=difficulty, inline=True)
        self.add_field(
            name="▶️ Quick Start",
            value=f"Type `/play {game_id}` to start a game!",
            inline=False
        )
        self.add_field(name="👤 Created by", value=author, inline=True)


class MatchmakingEmbed(CustomEmbed):
    """Enhanced matchmaking lobby embed with clear information."""
    
    def __init__(self, game_name: str, game_id: str, creator, players: list, 
                 min_players: int, max_players: int, rated: bool = True, private: bool = False):
        status = "Private" if private else "Public"
        rating_status = "Rated" if rated else "Unrated"
        
        super().__init__(
            title=f"🎮 {game_name} Lobby",
            description=(
                f"**{creator.display_name}** is looking for players!\n"
                f"Click **Join** to enter the lobby."
            ),
            color=MATCHMAKING_COLOR
        )
        
        # Player list
        if players:
            player_list = "\n".join([f"• {p.display_name}" for p in players])
        else:
            player_list = "*No players yet*"
        
        self.add_field(
            name=f"👥 Players ({len(players)}/{max_players})",
            value=player_list,
            inline=True
        )
        self.add_field(
            name="📋 Game Info",
            value=f"**Mode:** {status} • {rating_status}\n**Need:** {min_players}-{max_players} players",
            inline=True
        )
        
        if len(players) >= min_players:
            self.add_field(
                name="✅ Ready to Start!",
                value="The creator can click **Start** to begin.",
                inline=False
            )
        else:
            needed = min_players - len(players)
            self.add_field(
                name=f"⏳ Waiting for {needed} more player{'s' if needed > 1 else ''}",
                value="Invite friends or wait for others to join!",
                inline=False
            )


class FirstTimeUserEmbed(CustomEmbed):
    """Welcome embed for first-time users with tutorial guidance."""
    
    def __init__(self, game_name: str = None):
        super().__init__(
            title=f"🎉 Welcome to {NAME}!",
            description=(
                "Looks like this is your first time playing! Here's a quick guide to get you started."
            ),
            color=SUCCESS_COLOR
        )
        
        self.add_field(
            name="🎮 How Games Work",
            value=(
                "1. **Join or Create** - Join a lobby or create one with `/play <game>`\n"
                "2. **Wait for Players** - Once enough players join, the creator starts the game\n"
                "3. **Play!** - Follow the on-screen buttons and instructions to play"
            ),
            inline=False
        )
        
        self.add_field(
            name="⭐ Ratings & Leaderboards",
            value=(
                "Every rated game affects your skill rating. Win games to climb the leaderboard!\n"
                "Check your stats anytime with `/playcord profile`."
            ),
            inline=False
        )
        
        self.add_field(
            name="💡 Pro Tips",
            value=(
                "• Use **buttons** instead of typing when available - it's faster!\n"
                "• Invite friends with `/playcord invite @user`\n"
                "• Need help? Use `/playcord help` anytime"
            ),
            inline=False
        )
        
        if game_name:
            self.add_field(
                name=f"▶️ Ready to Play {game_name}?",
                value="Good luck and have fun! 🍀",
                inline=False
            )
