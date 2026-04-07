import discord
from discord import SelectOption

from configuration.constants import BUTTON_PREFIX_LOBBY_OPT, BUTTON_PREFIX_LOBBY_ROLE, EMBED_COLOR
from utils.containers import (
    CustomContainer,
    HelpCommandsContainer,
    HelpGettingStartedContainer,
    HelpMainContainer,
    container_to_markdown,
)
from utils.emojis import get_button_emoji
from utils.locale import get


def container_to_view_text(container: CustomContainer | str | None) -> str:
    return container_to_markdown(container)


class DynamicButtonView(discord.ui.LayoutView):
    """
    Dynamic button view: this is PAIN
    """

    def __init__(
        self,
        buttons: list[dict],
        summary_text: str | None = None,
        table_image_url: str | None = None,
    ) -> None:
        """
        Create a dynamic button view
        :param buttons: list of buttons as dictionaries
        look at class D
        """
        super().__init__(timeout=None)
        container = None
        if summary_text or table_image_url:
            container = discord.ui.Container()
            if summary_text:
                container.add_item(discord.ui.TextDisplay(summary_text[:4000]))
            if table_image_url:
                if summary_text:
                    container.add_item(discord.ui.Separator())
                container.add_item(
                    discord.ui.MediaGallery(
                        discord.MediaGalleryItem(table_image_url),
                    )
                )
            # Keep buttons inside the container when present
            self.add_item(container)

        row = discord.ui.ActionRow()
        count = 0
        for button in buttons:
            for argument in ["label", "style", "id", "emoji", "disabled", "callback", "link"]:
                if argument not in button.keys():
                    if argument == "disabled":
                        button[argument] = False
                        continue
                    button[argument] = None

            item = discord.ui.Button(
                label=button["label"],
                style=button["style"],
                custom_id=button["id"],
                emoji=button["emoji"],
                disabled=button["disabled"],
                url=button["link"],
            )
            if button["callback"] is None:
                item.callback = self._fail_callback
            elif button["callback"] == "none":
                item.callback = self._null_callback
            else:
                item.callback = button["callback"]
            row.add_item(item)
            count += 1
            if count == 5:
                self.add_item(row)
                row = discord.ui.ActionRow()
                count = 0
        if count:
            # If a container exists, add the action row to it so buttons appear inside the container
            if container is not None:
                container.add_item(row)
            else:
                self.add_item(row)

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
        for child in self.walk_children():
            if hasattr(child, "disabled"):
                child.disabled = True

        await interaction.response.edit_message(view=self)

        msg = await interaction.followup.send(content=get("interactions.dead_view"), ephemeral=True)

        await msg.delete(delay=10)  # autodelete message


class MatchmakingView(DynamicButtonView):
    """
    View for matchmaking message
    """

    def __init__(
        self,
        join_button_id=None,
        leave_button_id=None,
        start_button_id=None,
        can_start=True,
        summary_text: str | None = None,
        table_image_url: str | None = None,
    ) -> None:
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
        ], summary_text=summary_text, table_image_url=table_image_url)


class MatchmakingLobbyView(discord.ui.LayoutView):
    """
    Join / leave / start, optional string selects for per-game lobby settings (creator-only),
    and optional per-player role selects for games with CHOSEN role mode.
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
        option_specs: tuple = (),
        current_values: dict[str, str | int] | None = None,
        role_specs: list[tuple[int, str, tuple[str, ...]]] | None = None,
        current_role_values: dict[int, str] | None = None,
        summary_text: str | None = None,
        table_image_url: str | None = None,
    ) -> None:
        super().__init__(timeout=None)
        current_values = dict(current_values) if current_values else {}
        current_role_values = dict(current_role_values) if current_role_values else {}
        role_specs = role_specs or []

        container = discord.ui.Container(discord.ui.TextDisplay("### Lobby Actions"))
        if summary_text:
            container.add_item(discord.ui.TextDisplay(summary_text[:4000]))
        if table_image_url:
            if summary_text:
                container.add_item(discord.ui.Separator())
            container.add_item(
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(table_image_url),
                )
            )
        if summary_text or table_image_url:
            container.add_item(discord.ui.Separator())

        action_row = discord.ui.ActionRow()
        join_btn = discord.ui.Button(
            label=get("buttons.join"),
            style=discord.ButtonStyle.gray,
            custom_id=join_button_id,
            emoji=get_button_emoji("join"),
        )
        join_btn.callback = self._route_to_cog
        action_row.add_item(join_btn)

        leave_btn = discord.ui.Button(
            label=get("buttons.leave"),
            style=discord.ButtonStyle.gray,
            custom_id=leave_button_id,
            emoji=get_button_emoji("leave"),
        )
        leave_btn.callback = self._route_to_cog
        action_row.add_item(leave_btn)

        start_btn = discord.ui.Button(
            label=get("buttons.start"),
            style=discord.ButtonStyle.blurple,
            custom_id=start_button_id,
            emoji=get_button_emoji("start"),
            disabled=not can_start,
        )
        start_btn.callback = self._route_to_cog
        action_row.add_item(start_btn)
        container.add_item(action_row)

        if option_specs:
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay("### Match Options"))

        for spec in option_specs:
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
            )
            sel.callback = self._route_to_cog
            option_row = discord.ui.ActionRow()
            option_row.add_item(sel)
            container.add_item(option_row)

        if role_specs:
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay("### Role Selection"))
        for player_id, display_name, avail_roles in role_specs:
            cur = current_role_values.get(player_id)
            roptions: list[SelectOption] = []
            for r in avail_roles:
                rv = str(r)[:100]
                roptions.append(
                    SelectOption(
                        label=str(r).replace("_", " ").title()[:100],
                        value=rv,
                        default=(cur is not None and str(cur) == str(r)),
                    )
                )
            placeholder = f"{display_name[:80]}: role"
            rsel = discord.ui.Select(
                custom_id=f"{BUTTON_PREFIX_LOBBY_ROLE}{lobby_message_id}/{player_id}",
                placeholder=placeholder[:150],
                min_values=1,
                max_values=1,
                options=roptions,
            )
            rsel.callback = self._route_to_cog
            role_row = discord.ui.ActionRow()
            role_row.add_item(rsel)
            container.add_item(role_row)

        self.add_item(container)


class InviteView(DynamicButtonView):
    """
    View for invitation DM
    """

    def __init__(self, join_button_id=None, game_link=None, summary_text: str | None = None) -> None:
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
        ], summary_text=summary_text)


class SpectateView(DynamicButtonView):
    """
    View for status message
    """

    def __init__(self, spectate_button_id=None, peek_button_id=None, game_link=None, summary_text: str | None = None) -> None:
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
        ], summary_text=summary_text)


class PaginationView(discord.ui.LayoutView):
    """
    Pagination with First/Previous/Next/Last (timeout=None). Button custom_ids carry only
    guild_id/user_id for ownership checks; page state lives on this view instance.
    If the view is not registered (e.g. after restart), GamesCog.on_interaction replies ephemerally.
    """

    def __init__(self, guild_id: int, user_id: int, current_page: int,
                 max_pages: int, callback_handler, body_text: str | None = None):
        """
        :param guild_id: Guild ID for validation (0 if not in a guild)
        :param user_id: User who invoked the command (only they can use the buttons)
        :param current_page: Current page (1-indexed)
        :param max_pages: Total pages
        :param callback_handler: async (interaction, new_page) -> None
        """
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self.current_page = current_page
        self.max_pages = max_pages
        self.callback_handler = callback_handler
        if body_text:
            self.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay(body_text[:4000]),
                    accent_color=EMBED_COLOR,
                )
            )

        from configuration.constants import (
            BUTTON_PREFIX_PAGINATION_FIRST,
            BUTTON_PREFIX_PAGINATION_PREV,
            BUTTON_PREFIX_PAGINATION_NEXT,
            BUTTON_PREFIX_PAGINATION_LAST
        )

        self.add_item(discord.ui.TextDisplay(f"Page {current_page} of {max_pages}"))
        base = f"{guild_id}/{user_id}"
        row = discord.ui.ActionRow()
        buttons = [
            (
                get("buttons.first"),
                "⏮️",
                discord.ButtonStyle.gray,
                f"{BUTTON_PREFIX_PAGINATION_FIRST}{base}",
                current_page == 1,
                self._first_callback,
            ),
            (
                get("buttons.previous"),
                "◀️",
                discord.ButtonStyle.primary,
                f"{BUTTON_PREFIX_PAGINATION_PREV}{base}",
                current_page == 1,
                self._prev_callback,
            ),
            (
                get("buttons.next"),
                "▶️",
                discord.ButtonStyle.primary,
                f"{BUTTON_PREFIX_PAGINATION_NEXT}{base}",
                current_page >= max_pages,
                self._next_callback,
            ),
            (
                get("buttons.last"),
                "⏭️",
                discord.ButtonStyle.gray,
                f"{BUTTON_PREFIX_PAGINATION_LAST}{base}",
                current_page >= max_pages,
                self._last_callback,
            ),
        ]
        for label, emoji, style, custom_id, disabled, callback in buttons:
            button = discord.ui.Button(
                label=label,
                emoji=emoji,
                style=style,
                custom_id=custom_id,
                disabled=disabled,
            )
            button.callback = callback
            row.add_item(button)
        self.add_item(row)

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

    def __init__(self, match_id: int, summary_text: str | None = None):
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
        ], summary_text=summary_text)


class HelpView(discord.ui.LayoutView):
    """
    Interactive help menu with navigation buttons.
    """
    
    def __init__(self, user_id: int, current_section: str = "main", body_text: str | None = None):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.current_section = current_section
        self.body_text = body_text
        self._setup_buttons()
    
    def _setup_buttons(self):
        """Set up navigation buttons based on current section."""
        container = discord.ui.Container(
            discord.ui.TextDisplay("### Help Navigation"),
            accent_color=EMBED_COLOR,
        )
        if self.body_text:
            container.add_item(discord.ui.TextDisplay(self.body_text[:4000]))
            container.add_item(discord.ui.Separator())
        row = discord.ui.ActionRow()
        if self.current_section == "main":
            row.add_item(HelpButton(
                label=get("help.buttons.getting_started"),
                emoji="🚀",
                section="getting_started",
                style=discord.ButtonStyle.green,
                user_id=self.user_id
            ))
            row.add_item(HelpButton(
                label=get("help.buttons.game_list"),
                emoji="🎮",
                section="games",
                style=discord.ButtonStyle.primary,
                user_id=self.user_id
            ))
            row.add_item(HelpButton(
                label=get("help.buttons.commands"),
                emoji="⚙️",
                section="commands",
                style=discord.ButtonStyle.primary,
                user_id=self.user_id
            ))
        else:
            row.add_item(HelpButton(
                label=get("help.buttons.back_to_help"),
                emoji="🏠",
                section="main",
                style=discord.ButtonStyle.gray,
                user_id=self.user_id
            ))
            
            if self.current_section == "games":
                row.add_item(HelpButton(
                    label=get("help.buttons.view_catalog"),
                    emoji="📖",
                    section="catalog",
                    style=discord.ButtonStyle.primary,
                    user_id=self.user_id
                ))
        container.add_item(row)
        self.add_item(container)


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
        
        
        if self.section == "main":
            container = HelpMainContainer()
        elif self.section == "getting_started":
            container = HelpGettingStartedContainer()
        elif self.section == "commands":
            container = HelpCommandsContainer()
        elif self.section == "games":
            # Show a brief games overview
            container = await self._build_games_container()
        elif self.section == "catalog":
            # Redirect to catalog command
            await interaction.response.send_message(
                get("help.buttons.catalog_redirect"),
                ephemeral=True
            )
            return
        else:
            container = HelpMainContainer()
        
        view = HelpView(
            user_id=self.user_id,
            current_section=self.section,
            body_text=container_to_view_text(container),
        )
        await interaction.response.edit_message(view=view)
    
    async def _build_games_container(self):
        """Build a quick games overview container."""
        import importlib
        from configuration.constants import GAME_TYPES, INFO_COLOR
        
        container = CustomContainer(
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
        
        container.add_field(
            name=get("help.games_overview.field_games"),
            value="\n".join(games_text),
            inline=False
        )
        
        container.add_field(
            name=get("help.games_overview.field_tip"),
            value=get("help.games_overview.tip_value"),
            inline=False
        )
        
        return container


class ContextualHelpView(discord.ui.LayoutView):
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
        row = discord.ui.ActionRow()
        button = discord.ui.Button(
            label=get("buttons.need_help"),
            emoji="❓",
            style=discord.ButtonStyle.secondary,
        )
        button.callback = self.help_button
        row.add_item(button)
        self.add_item(row)

    async def help_button(self, interaction: discord.Interaction):
        """Show contextual help based on the topic."""
        if self.help_topic == "getting_started":
            container = HelpGettingStartedContainer()
        elif self.help_topic == "commands":
            container = HelpCommandsContainer()
        else:
            container = HelpMainContainer()
        
        await interaction.response.send_message(content=container_to_view_text(container), ephemeral=True)


class QuickActionsView(discord.ui.LayoutView):
    """
    A view with quick action buttons for common operations.
    Can be added to profile, leaderboard, and other embeds.
    """
    
    def __init__(self, show_catalog: bool = True, show_help: bool = True, timeout: int = 180):
        super().__init__(timeout=timeout)
        row = discord.ui.ActionRow()
        if show_catalog:
            row.add_item(discord.ui.Button(
                label=get("buttons.view_catalog"),
                emoji="📖",
                style=discord.ButtonStyle.primary,
                custom_id="quick_catalog",
            ))
        
        if show_help:
            row.add_item(discord.ui.Button(
                label=get("buttons.get_help"),
                emoji="❓",
                style=discord.ButtonStyle.secondary,
                custom_id="quick_help",
            ))
        self.add_item(row)
