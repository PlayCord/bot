import discord
from discord import SelectOption

from configuration.constants import (
    BUTTON_PREFIX_LOBBY_OPT,
    BUTTON_PREFIX_LOBBY_ROLE,
    BUTTON_PREFIX_PAGINATION_FIRST,
    BUTTON_PREFIX_PAGINATION_LAST,
    BUTTON_PREFIX_PAGINATION_NEXT,
    BUTTON_PREFIX_PAGINATION_PREV,
    BUTTON_PREFIX_REMATCH,
    EPHEMERAL_DELETE_AFTER,
    GAME_TYPES,
    HELP_GAMES_PREVIEW_COUNT,
    INFO_COLOR,
)
from utils.discord_utils import followup_send, response_send_message
from utils.containers import (
    CustomContainer,
    HelpCommandsContainer,
    HelpFaqContainer,
    HelpGettingStartedContainer,
    HelpTutorialsContainer,
    HelpMainContainer,
    TEXT_DISPLAY_MAX,
    container_to_markdown,
)
from utils.locale import fmt, get


async def _noop_button_interaction(interaction: discord.Interaction) -> None:
    """Placeholder callback for decorative buttons (e.g. link row)."""
    pass


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
        container = discord.ui.Container()
        if summary_text:
            container.add_item(discord.ui.TextDisplay(summary_text[:TEXT_DISPLAY_MAX]))
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

        row = discord.ui.ActionRow()
        count = 0
        for button in buttons:
            for argument in ["label", "style", "id", "disabled", "callback", "link"]:
                if argument not in button:
                    if argument == "disabled":
                        button[argument] = False
                        continue
                    button[argument] = None

            item = discord.ui.Button(
                label=button["label"],
                style=button["style"],
                custom_id=button["id"],
                disabled=button["disabled"],
                url=button["link"],
            )
            if button["callback"] is None:
                item.callback = self._fail_callback
            elif button["callback"] == "none":
                item.callback = _noop_button_interaction
            else:
                item.callback = button["callback"]
            row.add_item(item)
            count += 1
            if count == 5:
                container.add_item(row)
                row = discord.ui.ActionRow()
                count = 0
        if count:
            container.add_item(row)
        self.add_item(container)

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

        await followup_send(
            interaction,
            content=get("interactions.dead_view"),
            ephemeral=True,
            delete_after=EPHEMERAL_DELETE_AFTER,
        )


class MatchmakingView(DynamicButtonView):
    """
    View for matchmaking message
    """

    def __init__(
        self,
        join_button_id=None,
        leave_button_id=None,
        ready_button_id=None,
        ready_button_label: str | None = None,
        summary_text: str | None = None,
        table_image_url: str | None = None,
    ) -> None:
        """
        Create a matchmaking view (Join / Leave / optional Ready — no Start; game begins when all ready).
        """
        buttons: list[dict] = [
            {
                "label": get("buttons.join"),
                "style": discord.ButtonStyle.gray,
                "id": join_button_id,
                "callback": "none",
            },
            {
                "label": get("buttons.leave"),
                "style": discord.ButtonStyle.gray,
                "id": leave_button_id,
                "callback": "none",
            },
        ]
        if ready_button_id is not None:
            buttons.append(
                {
                    "label": ready_button_label or get("buttons.ready"),
                    "style": discord.ButtonStyle.success,
                    "id": ready_button_id,
                    "callback": "none",
                }
            )
        super().__init__(
            buttons, summary_text=summary_text, table_image_url=table_image_url
        )


class MatchmakingLobbyView(discord.ui.LayoutView):
    """
    Join / leave / optional Ready, optional string selects for per-game lobby settings (creator-only),
    and optional per-player role selects for games with CHOSEN role mode. (Game starts when all humans ready.)
    """

    async def _route_to_cog(self, interaction: discord.Interaction) -> None:
        """Persistent components are handled in MatchmakingCog.on_interaction."""
        pass

    def __init__(
        self,
        join_button_id: str,
        leave_button_id: str,
        ready_button_id: str | None,
        ready_button_label: str,
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

        container = discord.ui.Container()
        if summary_text:
            container.add_item(discord.ui.TextDisplay(summary_text[:TEXT_DISPLAY_MAX]))
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
        )
        join_btn.callback = self._route_to_cog
        action_row.add_item(join_btn)

        leave_btn = discord.ui.Button(
            label=get("buttons.leave"),
            style=discord.ButtonStyle.gray,
            custom_id=leave_button_id,
        )
        leave_btn.callback = self._route_to_cog
        action_row.add_item(leave_btn)

        if ready_button_id is not None:
            ready_btn = discord.ui.Button(
                label=ready_button_label,
                style=discord.ButtonStyle.success,
                custom_id=ready_button_id,
            )
            ready_btn.callback = self._route_to_cog
            action_row.add_item(ready_btn)

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

    def __init__(
        self, join_button_id=None, game_link=None, summary_text: str | None = None
    ) -> None:
        """
        Create a invite view
        :param join_button_id: the custom ID of the join button
        :param game_link: the link to the game
        """
        super().__init__(
            [
                {
                    "label": get("buttons.join_game"),
                    "style": discord.ButtonStyle.blurple,
                    "id": join_button_id,
                    "callback": "none",
                },
                {
                    "label": get("buttons.go_to_game"),
                    "style": discord.ButtonStyle.gray,
                    "link": game_link,
                },
            ],
            summary_text=summary_text,
        )


class SpectateView(DynamicButtonView):
    """
    View for status message
    """

    def __init__(
        self,
        spectate_button_id=None,
        peek_button_id=None,
        game_link=None,
        summary_text: str | None = None,
        table_image_url: str | None = None,
    ) -> None:
        """
        Create a spectate view
        :param spectate_button_id: custom ID of the spectate button
        :param peek_button_id: custom ID of the peek button
        :param game_link: the link to the game
        :param table_image_url: optional attachment:// URL for overview table (same slot as DynamicButtonView)
        """
        buttons = [
            {
                "label": get("buttons.spectate"),
                "style": discord.ButtonStyle.blurple,
                "id": spectate_button_id,
                "callback": "none",
            },
        ]
        if peek_button_id:
            buttons.append(
                {
                    "label": get("buttons.peek"),
                    "style": discord.ButtonStyle.gray,
                    "id": peek_button_id,
                    "callback": "none",
                }
            )
        buttons.append(
            {
                "label": get("buttons.go_to_game"),
                "style": discord.ButtonStyle.gray,
                "link": game_link,
            }
        )
        super().__init__(
            buttons, summary_text=summary_text, table_image_url=table_image_url
        )


class PaginationView(discord.ui.LayoutView):
    """
    Pagination with First/Previous/Next/Last (timeout=None). Button custom_ids carry only
    guild_id/user_id for ownership checks; page state lives on this view instance.
    If the view is not registered (e.g. after restart), GamesCog.on_interaction replies ephemerally.
    """

    def __init__(
        self,
        guild_id: int,
        user_id: int,
        current_page: int,
        max_pages: int,
        callback_handler,
        body_text: str | None = None,
    ):
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
        container = discord.ui.Container()
        if body_text:
            container.add_item(discord.ui.TextDisplay(body_text[:TEXT_DISPLAY_MAX]))
            container.add_item(discord.ui.Separator())

        base = f"{guild_id}/{user_id}"
        row = discord.ui.ActionRow()
        buttons = [
            (
                get("buttons.first"),
                discord.ButtonStyle.gray,
                f"{BUTTON_PREFIX_PAGINATION_FIRST}{base}",
                current_page == 1,
                self._first_callback,
            ),
            (
                get("buttons.previous"),
                discord.ButtonStyle.primary,
                f"{BUTTON_PREFIX_PAGINATION_PREV}{base}",
                current_page == 1,
                self._prev_callback,
            ),
            (
                get("buttons.next"),
                discord.ButtonStyle.primary,
                f"{BUTTON_PREFIX_PAGINATION_NEXT}{base}",
                current_page >= max_pages,
                self._next_callback,
            ),
            (
                get("buttons.last"),
                discord.ButtonStyle.gray,
                f"{BUTTON_PREFIX_PAGINATION_LAST}{base}",
                current_page >= max_pages,
                self._last_callback,
            ),
        ]
        for label, style, custom_id, disabled, callback in buttons:
            button = discord.ui.Button(
                label=label,
                style=style,
                custom_id=custom_id,
                disabled=disabled,
            )
            button.callback = callback
            row.add_item(button)
        container.add_item(row)
        self.add_item(container)

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
            await response_send_message(
                interaction,
                get("interactions.pagination_not_yours"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        await interaction.response.defer()
        await self.callback_handler(interaction, 1)

    async def _prev_callback(self, interaction: discord.Interaction):
        """Navigate to previous page."""
        if not self._validate_interaction(interaction):
            await response_send_message(
                interaction,
                get("interactions.pagination_not_yours"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        new_page = max(1, self.current_page - 1)
        await interaction.response.defer()
        await self.callback_handler(interaction, new_page)

    async def _next_callback(self, interaction: discord.Interaction):
        """Navigate to next page."""
        if not self._validate_interaction(interaction):
            await response_send_message(
                interaction,
                get("interactions.pagination_not_yours"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        new_page = min(self.max_pages, self.current_page + 1)
        await interaction.response.defer()
        await self.callback_handler(interaction, new_page)

    async def _last_callback(self, interaction: discord.Interaction):
        """Navigate to last page."""
        if not self._validate_interaction(interaction):
            await response_send_message(
                interaction,
                get("interactions.pagination_not_yours"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        await interaction.response.defer()
        await self.callback_handler(interaction, self.max_pages)


class RematchView(DynamicButtonView):
    """Rematch button; interaction is handled in GamesCog (see callback \"none\")."""

    def __init__(self, match_id: int, summary_text: str | None = None):
        super().__init__(
            [
                {
                    "label": get("buttons.rematch"),
                    "style": discord.ButtonStyle.success,
                    "id": f"{BUTTON_PREFIX_REMATCH}{match_id}",
                    "disabled": False,
                    "callback": "none",
                },
            ],
            summary_text=summary_text,
        )


class HelpView(discord.ui.LayoutView):
    """
    Interactive help menu with navigation buttons.
    """

    def __init__(
        self, user_id: int, current_section: str = "main", body_text: str | None = None
    ):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.current_section = current_section
        self.body_text = body_text
        self._setup_buttons()

    def _setup_buttons(self):
        """Set up navigation buttons based on current section."""
        container = discord.ui.Container(
            discord.ui.TextDisplay("### Help Navigation"),
        )
        if self.body_text:
            container.add_item(
                discord.ui.TextDisplay(self.body_text[:TEXT_DISPLAY_MAX])
            )
            container.add_item(discord.ui.Separator())
        row = discord.ui.ActionRow()
        if self.current_section == "main":
            row.add_item(
                HelpButton(
                    label=get("help.buttons.getting_started"),
                    section="getting_started",
                    style=discord.ButtonStyle.green,
                    user_id=self.user_id,
                )
            )
            row.add_item(
                HelpButton(
                    label=get("help.buttons.game_list"),
                    section="games",
                    style=discord.ButtonStyle.primary,
                    user_id=self.user_id,
                )
            )
            row.add_item(
                HelpButton(
                    label=get("help.buttons.commands"),
                    section="commands",
                    style=discord.ButtonStyle.primary,
                    user_id=self.user_id,
                )
            )
            row.add_item(
                HelpButton(
                    label=get("help.buttons.game_tutorials"),
                    section="tutorials",
                    style=discord.ButtonStyle.secondary,
                    user_id=self.user_id,
                )
            )
            row.add_item(
                HelpButton(
                    label=get("help.buttons.faq"),
                    section="faq",
                    style=discord.ButtonStyle.secondary,
                    user_id=self.user_id,
                )
            )
        else:
            row.add_item(
                HelpButton(
                    label=get("help.buttons.back_to_help"),
                    section="main",
                    style=discord.ButtonStyle.gray,
                    user_id=self.user_id,
                )
            )

            if self.current_section == "games":
                row.add_item(
                    HelpButton(
                        label=get("help.buttons.view_catalog"),
                        section="catalog",
                        style=discord.ButtonStyle.primary,
                        user_id=self.user_id,
                    )
                )
            elif self.current_section == "tutorials":
                row.add_item(
                    HelpButton(
                        label=get("help.buttons.game_list"),
                        section="games",
                        style=discord.ButtonStyle.primary,
                        user_id=self.user_id,
                    )
                )
        container.add_item(row)
        if self.current_section == "tutorials":
            game_row = discord.ui.ActionRow()
            for game_id in list(GAME_TYPES)[:5]:
                game_row.add_item(
                    GameTutorialButton(game_id=game_id, user_id=self.user_id)
                )
            container.add_item(game_row)
        self.add_item(container)


class HelpButton(discord.ui.Button):
    """Button for help menu navigation."""

    def __init__(
        self, label: str, section: str, style: discord.ButtonStyle, user_id: int
    ):
        super().__init__(label=label, style=style)
        self.section = section
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await response_send_message(
                interaction,
                get("interactions.help_not_yours"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        if self.section == "main":
            container = HelpMainContainer()
        elif self.section == "getting_started":
            container = HelpGettingStartedContainer()
        elif self.section == "commands":
            container = HelpCommandsContainer()
        elif self.section == "faq":
            container = HelpFaqContainer()
        elif self.section == "games":
            # Show a brief games overview
            container = await self._build_games_container()
        elif self.section == "tutorials":
            container = HelpTutorialsContainer()
        elif self.section == "catalog":
            # Redirect to catalog command
            await response_send_message(
                interaction,
                get("help.buttons.catalog_redirect"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        else:
            container = HelpMainContainer()

        view = HelpView(
            user_id=self.user_id,
            current_section=self.section,
            body_text=container_to_markdown(container),
        )
        await interaction.response.edit_message(view=view)

    async def _build_games_container(self):
        """Build a quick games overview container."""
        import importlib

        container = CustomContainer(
            title=get("help.games_overview.title"),
            description=get("help.games_overview.description"),
            color=INFO_COLOR,
        )

        games_text = []
        for game_id, (module_name, class_name) in list(GAME_TYPES.items())[
            :HELP_GAMES_PREVIEW_COUNT
        ]:
            game_class = getattr(importlib.import_module(module_name), class_name)
            game_name = getattr(game_class, "name", game_id)
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
                )
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


class GameTutorialButton(discord.ui.Button):
    def __init__(self, game_id: str, user_id: int):
        super().__init__(label=game_id[:80], style=discord.ButtonStyle.primary)
        self.game_id = game_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await response_send_message(
                interaction,
                get("interactions.help_not_yours"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        import importlib
        from utils.containers import HelpGameInfoContainer

        module_name, class_name = GAME_TYPES[self.game_id]
        game_class = getattr(importlib.import_module(module_name), class_name)
        container = HelpGameInfoContainer(self.game_id, game_class)
        view = HelpView(
            user_id=self.user_id,
            current_section="tutorials",
            body_text=container_to_markdown(container),
        )
        await interaction.response.edit_message(view=view)


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
        container = discord.ui.Container(discord.ui.TextDisplay("### Help"))
        row = discord.ui.ActionRow()
        button = discord.ui.Button(
            label=get("buttons.need_help"),
            style=discord.ButtonStyle.secondary,
        )
        button.callback = self.help_button
        row.add_item(button)
        container.add_item(row)
        self.add_item(container)

    async def help_button(self, interaction: discord.Interaction):
        """Show contextual help based on the topic."""
        if self.help_topic == "getting_started":
            container = HelpGettingStartedContainer()
        elif self.help_topic == "commands":
            container = HelpCommandsContainer()
        else:
            container = HelpMainContainer()

        await response_send_message(
            interaction,
            content=container_to_markdown(container),
            ephemeral=True,
            delete_after=EPHEMERAL_DELETE_AFTER,
        )


class QuickActionsView(discord.ui.LayoutView):
    """
    A view with quick action buttons for common operations.
    Can be added to profile, leaderboard, and other embeds.
    """

    def __init__(
        self, show_catalog: bool = True, show_help: bool = True, timeout: int = 180
    ):
        super().__init__(timeout=timeout)
        container = discord.ui.Container(discord.ui.TextDisplay("### Quick Actions"))
        row = discord.ui.ActionRow()
        if show_catalog:
            row.add_item(
                discord.ui.Button(
                    label=get("buttons.view_catalog"),
                    style=discord.ButtonStyle.primary,
                    custom_id="quick_catalog",
                )
            )

        if show_help:
            row.add_item(
                discord.ui.Button(
                    label=get("buttons.get_help"),
                    style=discord.ButtonStyle.secondary,
                    custom_id="quick_help",
                )
            )
        container.add_item(row)
        self.add_item(container)
