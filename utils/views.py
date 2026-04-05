import discord
from discord import SelectOption

from configuration.constants import BUTTON_PREFIX_LOBBY_OPT
from utils.emojis import get_button_emoji
from utils.locale import get


class DynamicButtonView(discord.ui.View):
    """
    Dynamic button view: this is PAIN
    """

    def __init__(self, buttons: list[dict]) -> None:
        """
        Create a dynamic button view
        :param buttons: list of buttons as dictionaries
        look at class D
        """
        super().__init__(timeout=None)  # timeout=None required for persistent views, per discord docs

        # Register buttons to view
        for button in buttons:
            for argument in ["label", "style", "id", "emoji", "disabled", "callback", "link"]:
                if argument not in button.keys():
                    if argument == "disabled":
                        button[argument] = False
                        continue
                    button[argument] = None

            item = discord.ui.Button(label=button["label"], style=button["style"],
                                     custom_id=button["id"], emoji=button["emoji"], disabled=button["disabled"],
                                     url=button["link"])
            if button["callback"] is None:
                item.callback = self._fail_callback
            elif button["callback"] == "none":
                item.callback = self._null_callback
            else:
                item.callback = button["callback"]

            self.add_item(item)

    async def _null_callback(self, interaction: discord.Interaction) -> None:
        """
        Null callback
        :param interaction: discord context
        :return: Nothing
        """
        pass

    async def _fail_callback(self, interaction: discord.Interaction) -> None:
        """
        If a "dead" view is interacted, simply disable each component and update the message
        also send an ephemeral message to the interacter
        :param interaction: discord context
        :return: nothing
        """
        embed = interaction.message.embeds[0]  # There can only be one... embed :O

        for child in self.children:  # Disable all children via drop kicking
            child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)  # Update message, because you can't autoupdate

        msg = await interaction.followup.send(content=get("interactions.dead_view"), ephemeral=True)

        await msg.delete(delay=10)  # autodelete message


class MatchmakingView(DynamicButtonView):
    """
    View for matchmaking message
    """

    def __init__(self, join_button_id=None, leave_button_id=None,
                 start_button_id=None, can_start=True) -> None:
        """
        Create a matchmaking view
        :param join_button_id: id of the join button
        :param leave_button_id: id of the leave button
        :param start_button_id: id of the start button
        :param can_start: whether the game can be started
        """
        super().__init__([
            {"label": get("buttons.join"), "style": discord.ButtonStyle.gray, "id": join_button_id,
             "emoji": get_button_emoji("join"), "callback": "none"},
            {"label": get("buttons.leave"), "style": discord.ButtonStyle.gray, "id": leave_button_id,
             "emoji": get_button_emoji("leave"), "callback": "none"},
            {"label": get("buttons.start"), "style": discord.ButtonStyle.blurple, "id": start_button_id,
             "emoji": get_button_emoji("start"), "callback": "none", "disabled": not can_start}
        ])


class MatchmakingLobbyView(discord.ui.View):
    """
    Join / leave / start plus optional string selects for per-game lobby settings (creator-only).
    """

    async def _route_to_cog(self, interaction: discord.Interaction) -> None:
        """Persistent components are handled in MatchmakingCog.on_interaction."""
        pass

    def __init__(
        self,
        join_button_id: str,
        leave_button_id: str,
        start_button_id: str,
        can_start: bool,
        lobby_message_id: int,
        option_specs: tuple,
        current_values: dict[str, str | int],
    ) -> None:
        super().__init__(timeout=None)

        join_btn = discord.ui.Button(
            label=get("buttons.join"),
            style=discord.ButtonStyle.gray,
            custom_id=join_button_id,
            emoji=get_button_emoji("join"),
            row=0,
        )
        join_btn.callback = self._route_to_cog
        self.add_item(join_btn)

        leave_btn = discord.ui.Button(
            label=get("buttons.leave"),
            style=discord.ButtonStyle.gray,
            custom_id=leave_button_id,
            emoji=get_button_emoji("leave"),
            row=0,
        )
        leave_btn.callback = self._route_to_cog
        self.add_item(leave_btn)

        start_btn = discord.ui.Button(
            label=get("buttons.start"),
            style=discord.ButtonStyle.blurple,
            custom_id=start_button_id,
            emoji=get_button_emoji("start"),
            disabled=not can_start,
            row=0,
        )
        start_btn.callback = self._route_to_cog
        self.add_item(start_btn)

        for row, spec in enumerate(option_specs, start=1):
            if row > 4:
                break
            cur = current_values.get(spec.key, spec.default)
            options: list[SelectOption] = []
            for label, value, is_def in spec.select_options():
                options.append(
                    SelectOption(
                        label=label[:100],
                        value=value[:100],
                        default=(str(value) == str(cur)),
                    )
                )
            sel = discord.ui.Select(
                custom_id=f"{BUTTON_PREFIX_LOBBY_OPT}{lobby_message_id}/{spec.key}",
                placeholder=spec.label[:150],
                min_values=1,
                max_values=1,
                options=options,
                row=row,
            )
            sel.callback = self._route_to_cog
            self.add_item(sel)


class InviteView(DynamicButtonView):
    """
    View for invitation DM
    """

    def __init__(self, join_button_id=None, game_link=None) -> None:
        """
        Create a invite view
        :param join_button_id: the custom ID of the join button
        :param game_link: the link to the game
        """
        super().__init__([
            {"label": get("buttons.join_game"), "style": discord.ButtonStyle.blurple,
             "id": join_button_id, "emoji": get_button_emoji("join"), "callback": "none"},
            {"label": get("buttons.go_to_game"),
             "style": discord.ButtonStyle.gray, "link": game_link}
        ])


class SpectateView(DynamicButtonView):
    """
    View for status message
    """

    def __init__(self, spectate_button_id=None, peek_button_id=None, game_link=None) -> None:
        """
        Create a spectate view
        :param spectate_button_id: custom ID of the spectate button
        :param peek_button_id: custom ID of the peek button
        :param game_link: the link to the game
        """
        super().__init__([
            {"label": get("buttons.spectate"), "style": discord.ButtonStyle.blurple,
             "id": spectate_button_id, "emoji": get_button_emoji("spectate"), "callback": "none"},
            {"label": get("buttons.peek"), "style": discord.ButtonStyle.gray, "id": peek_button_id,
             "emoji": get_button_emoji("peek"), "callback": "none"},
            {"label": get("buttons.go_to_game"), "style": discord.ButtonStyle.gray,
             "link": game_link}
        ])


class PaginationView(DynamicButtonView):
    """
    Pagination with First/Previous/Next/Last (timeout=None). Button custom_ids carry only
    guild_id/user_id for ownership checks; page state lives on this view instance.
    If the view is not registered (e.g. after restart), GamesCog.on_interaction replies ephemerally.
    """

    def __init__(self, guild_id: int, user_id: int, current_page: int,
                 max_pages: int, callback_handler):
        """
        :param guild_id: Guild ID for validation (0 if not in a guild)
        :param user_id: User who invoked the command (only they can use the buttons)
        :param current_page: Current page (1-indexed)
        :param max_pages: Total pages
        :param callback_handler: async (interaction, new_page) -> None
        """
        self.guild_id = guild_id
        self.user_id = user_id
        self.current_page = current_page
        self.max_pages = max_pages
        self.callback_handler = callback_handler

        from configuration.constants import (
            BUTTON_PREFIX_PAGINATION_FIRST,
            BUTTON_PREFIX_PAGINATION_PREV,
            BUTTON_PREFIX_PAGINATION_NEXT,
            BUTTON_PREFIX_PAGINATION_LAST
        )

        base = f"{guild_id}/{user_id}"
        super().__init__([
            {
                "label": get("buttons.first"),
                "emoji": "⏮️",
                "style": discord.ButtonStyle.gray,
                "id": f"{BUTTON_PREFIX_PAGINATION_FIRST}{base}",
                "disabled": (current_page == 1),
                "callback": self._first_callback,
            },
            {
                "label": get("buttons.previous"),
                "emoji": "◀️",
                "style": discord.ButtonStyle.primary,
                "id": f"{BUTTON_PREFIX_PAGINATION_PREV}{base}",
                "disabled": (current_page == 1),
                "callback": self._prev_callback,
            },
            {
                "label": get("buttons.next"),
                "emoji": "▶️",
                "style": discord.ButtonStyle.primary,
                "id": f"{BUTTON_PREFIX_PAGINATION_NEXT}{base}",
                "disabled": (current_page >= max_pages),
                "callback": self._next_callback,
            },
            {
                "label": get("buttons.last"),
                "emoji": "⏭️",
                "style": discord.ButtonStyle.gray,
                "id": f"{BUTTON_PREFIX_PAGINATION_LAST}{base}",
                "disabled": (current_page >= max_pages),
                "callback": self._last_callback,
            },
        ])

    def _validate_interaction(self, interaction: discord.Interaction) -> bool:
        """Validate that the interaction is from the command invoker."""
        if interaction.user.id != self.user_id:
            return False
        if interaction.guild_id != self.guild_id:
            return False
        return True

    async def _first_callback(self, interaction: discord.Interaction):
        """Navigate to first page."""
        if not self._validate_interaction(interaction):
            await interaction.response.send_message(
                get("interactions.pagination_not_yours"),
                ephemeral=True
            )
            return

        await interaction.response.defer()
        await self.callback_handler(interaction, 1)

    async def _prev_callback(self, interaction: discord.Interaction):
        """Navigate to previous page."""
        if not self._validate_interaction(interaction):
            await interaction.response.send_message(
                get("interactions.pagination_not_yours"),
                ephemeral=True
            )
            return

        new_page = max(1, self.current_page - 1)
        await interaction.response.defer()
        await self.callback_handler(interaction, new_page)

    async def _next_callback(self, interaction: discord.Interaction):
        """Navigate to next page."""
        if not self._validate_interaction(interaction):
            await interaction.response.send_message(
                get("interactions.pagination_not_yours"),
                ephemeral=True
            )
            return

        new_page = min(self.max_pages, self.current_page + 1)
        await interaction.response.defer()
        await self.callback_handler(interaction, new_page)

    async def _last_callback(self, interaction: discord.Interaction):
        """Navigate to last page."""
        if not self._validate_interaction(interaction):
            await interaction.response.send_message(
                get("interactions.pagination_not_yours"),
                ephemeral=True
            )
            return

        await interaction.response.defer()
        await self.callback_handler(interaction, self.max_pages)


class RematchView(DynamicButtonView):
    """Rematch button; interaction is handled in GamesCog (see callback \"none\")."""

    def __init__(self, match_id: int):
        from configuration.constants import BUTTON_PREFIX_REMATCH

        super().__init__([
            {
                "label": get("buttons.rematch"),
                "style": discord.ButtonStyle.success,
                "id": f"{BUTTON_PREFIX_REMATCH}{match_id}",
                "emoji": get_button_emoji("rematch"),
                "disabled": False,
                "callback": "none",
            },
        ])


class HelpView(discord.ui.View):
    """
    Interactive help menu with navigation buttons.
    """
    
    def __init__(self, user_id: int, current_section: str = "main"):
        super().__init__(timeout=300)  # 5 minute timeout
        self.user_id = user_id
        self.current_section = current_section
        self._setup_buttons()
    
    def _setup_buttons(self):
        """Set up navigation buttons based on current section."""
        from configuration.constants import INFO_COLOR
        
        # Main navigation buttons
        if self.current_section == "main":
            self.add_item(HelpButton(
                label=get("help.buttons.getting_started"),
                emoji="🚀",
                section="getting_started",
                style=discord.ButtonStyle.green,
                user_id=self.user_id
            ))
            self.add_item(HelpButton(
                label=get("help.buttons.game_list"),
                emoji="🎮",
                section="games",
                style=discord.ButtonStyle.primary,
                user_id=self.user_id
            ))
            self.add_item(HelpButton(
                label=get("help.buttons.commands"),
                emoji="⚙️",
                section="commands",
                style=discord.ButtonStyle.primary,
                user_id=self.user_id
            ))
        else:
            # Back button for sub-sections
            self.add_item(HelpButton(
                label=get("help.buttons.back_to_help"),
                emoji="🏠",
                section="main",
                style=discord.ButtonStyle.gray,
                user_id=self.user_id
            ))
            
            if self.current_section == "games":
                self.add_item(HelpButton(
                    label=get("help.buttons.view_catalog"),
                    emoji="📖",
                    section="catalog",
                    style=discord.ButtonStyle.primary,
                    user_id=self.user_id
                ))


class HelpButton(discord.ui.Button):
    """Button for help menu navigation."""
    
    def __init__(self, label: str, emoji: str, section: str, 
                 style: discord.ButtonStyle, user_id: int):
        super().__init__(label=label, emoji=emoji, style=style)
        self.section = section
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                get("interactions.help_not_yours"),
                ephemeral=True
            )
            return
        
        from utils.embeds import (
            HelpMainEmbed, HelpGettingStartedEmbed, HelpCommandsEmbed
        )
        
        if self.section == "main":
            embed = HelpMainEmbed()
        elif self.section == "getting_started":
            embed = HelpGettingStartedEmbed()
        elif self.section == "commands":
            embed = HelpCommandsEmbed()
        elif self.section == "games":
            # Show a brief games overview
            embed = await self._build_games_embed()
        elif self.section == "catalog":
            # Redirect to catalog command
            await interaction.response.send_message(
                get("help.buttons.catalog_redirect"),
                ephemeral=True
            )
            return
        else:
            embed = HelpMainEmbed()
        
        view = HelpView(user_id=self.user_id, current_section=self.section)
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def _build_games_embed(self):
        """Build a quick games overview embed."""
        import importlib
        from configuration.constants import GAME_TYPES, INFO_COLOR
        from utils.embeds import CustomEmbed
        
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
            games_text.append(get("help.games_overview.more_games").format(count=len(GAME_TYPES) - 8))
        
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


class ContextualHelpView(discord.ui.View):
    """
    A view with a contextual help button that can be added to any embed.
    Shows relevant help information based on the context.
    """
    
    def __init__(self, help_topic: str = "main", timeout: int = 180):
        """
        Initialize contextual help view.
        
        Args:
            help_topic: The help topic to show when clicked (main, games, commands, getting_started)
            timeout: View timeout in seconds
        """
        super().__init__(timeout=timeout)
        self.help_topic = help_topic
    
    @discord.ui.button(label=get("buttons.need_help"), emoji="❓", style=discord.ButtonStyle.secondary)
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show contextual help based on the topic."""
        from utils.embeds import (
            HelpMainEmbed, HelpGettingStartedEmbed, HelpCommandsEmbed
        )
        
        if self.help_topic == "getting_started":
            embed = HelpGettingStartedEmbed()
        elif self.help_topic == "commands":
            embed = HelpCommandsEmbed()
        else:
            embed = HelpMainEmbed()
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class QuickActionsView(discord.ui.View):
    """
    A view with quick action buttons for common operations.
    Can be added to profile, leaderboard, and other embeds.
    """
    
    def __init__(self, show_catalog: bool = True, show_help: bool = True, timeout: int = 180):
        super().__init__(timeout=timeout)
        
        if show_catalog:
            self.add_item(discord.ui.Button(
                label=get("buttons.view_catalog"),
                emoji="📖",
                style=discord.ButtonStyle.primary,
                custom_id="quick_catalog",
            ))
        
        if show_help:
            self.add_item(discord.ui.Button(
                label=get("buttons.get_help"),
                emoji="❓",
                style=discord.ButtonStyle.secondary,
                custom_id="quick_help",
            ))
