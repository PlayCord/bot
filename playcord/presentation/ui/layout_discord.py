"""Discord LayoutView and dynamic button views."""

from __future__ import annotations

from typing import Any

import discord
from discord import SelectOption

from playcord.api import RoleFlow, RoleMode
from playcord.infrastructure.constants import (
    BUTTON_PREFIX_PAGINATION_FIRST,
    BUTTON_PREFIX_PAGINATION_LAST,
    BUTTON_PREFIX_PAGINATION_NEXT,
    BUTTON_PREFIX_PAGINATION_PAGE,
    BUTTON_PREFIX_PAGINATION_PREV,
    BUTTON_PREFIX_REMATCH,
    EPHEMERAL_DELETE_AFTER,
)
from playcord.infrastructure.locale import fmt, get
from playcord.presentation.ui.component_kit import (
    icon_for_button,
    link_button,
    nav_row,
    primary_button,
    secondary_button,
)
from playcord.presentation.ui.presets import (
    append_blocks,
    button_row,
    media_block,
    summary_text_block,
    text_block,
    text_sections_block,
    title_block,
)
from playcord.ui.components import pagination_row
from playcord.ui.emojis import get_game_emoji, get_emoji_string, get_icon, parse_discord_emoji
from playcord.ui.emojis import resolve_button_emoji


async def followup_send(*args: Any, **kwargs: Any) -> Any:
    from playcord.presentation.interactions.helpers import followup_send as _send

    return await _send(*args, **kwargs)


async def response_send_message(*args: Any, **kwargs: Any) -> Any:
    from playcord.presentation.interactions.helpers import (
        response_send_message as _send,
    )

    return await _send(*args, **kwargs)


async def _noop_button_interaction(interaction: discord.Interaction) -> None:
    """Placeholder callback for decorative buttons (e.g. link row)."""


class AboutView(discord.ui.LayoutView):
    """About page with external link buttons in the bottom action row."""

    def __init__(
            self,
            bot: discord.Client,
            user_id: int,
            guild_id: int,
            body_text: str,
            attributions_text: str,
    ) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id
        self.guild_id = guild_id
        self.body_text = body_text
        self.attributions_text = attributions_text

        container = discord.ui.Container()
        body_text_clean = (body_text or "").strip()
        if body_text_clean:
            append_blocks(container, text_block(body_text_clean), has_content=False)
            container.add_item(discord.ui.Separator())
        github_url = get("brand.github_url")

        async def attributions_callback(interaction: discord.Interaction) -> None:
            if interaction.user.id != self.user_id or interaction.guild_id != self.guild_id:
                await response_send_message(
                    interaction,
                    get("interactions.about_not_yours"),
                    ephemeral=True,
                    delete_after=EPHEMERAL_DELETE_AFTER,
                )
                return

            attributions_view = AttributionsView(
                bot=self.bot,
                user_id=self.user_id,
                guild_id=self.guild_id,
                body_text=self.body_text,
                attributions_text=self.attributions_text,
            )
            await interaction.response.edit_message(view=attributions_view)

        row = nav_row(
            link_button(
                label=get("buttons.about_github"),
                url=github_url,
                icon="github",
            ),
            link_button(
                label=get("buttons.about_docs"),
                url=get("brand.readme_url"),
            ),
            link_button(
                label=get("buttons.about_issues"),
                url=f"{github_url}/issues",
            ),
            primary_button(
                label=get("buttons.about_attributions"),
                icon="info",
                callback=attributions_callback,
            ),
        )
        container.add_item(row)
        self.add_item(container)


class AttributionsView(discord.ui.LayoutView):
    """Attributions page with a back button."""

    def __init__(
            self,
            bot: discord.Client,
            user_id: int,
            guild_id: int,
            body_text: str,
            attributions_text: str,
    ) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id
        self.guild_id = guild_id
        self.body_text = body_text
        self.attributions_text = attributions_text

        container = discord.ui.Container()
        attributions_text_clean = (attributions_text or "").strip()
        if attributions_text_clean:
            append_blocks(container, text_block(attributions_text_clean), has_content=False)
            container.add_item(discord.ui.Separator())

        async def back_callback(interaction: discord.Interaction) -> None:
            if interaction.user.id != self.user_id or interaction.guild_id != self.guild_id:
                await response_send_message(
                    interaction,
                    get("interactions.about_not_yours"),
                    ephemeral=True,
                    delete_after=EPHEMERAL_DELETE_AFTER,
                )
                return

            about_view = AboutView(
                bot=self.bot,
                user_id=self.user_id,
                guild_id=self.guild_id,
                body_text=self.body_text,
                attributions_text=self.attributions_text,
            )
            await interaction.response.edit_message(view=about_view)

        row = nav_row(
            secondary_button(
                label=get("buttons.back"),
                icon="previous",
                callback=back_callback,
            ),
        )
        container.add_item(row)
        self.add_item(container)


class DynamicButtonView(discord.ui.LayoutView):
    """Dynamic button view: this is PAIN."""

    def __init__(
            self,
            buttons: list[dict],
            summary_text: str | None = None,
            text_sections: list[str] | None = None,
            table_image_url: str | None = None,
    ) -> None:
        """
        Create a dynamic button view
        :param buttons: list of buttons as dictionaries
        look at class D.
        """
        super().__init__(timeout=None)
        container = discord.ui.Container()
        has_content = False
        if text_sections:
            has_content = append_blocks(
                container,
                text_sections_block(text_sections),
                has_content=has_content,
            )
        elif summary_text:
            has_content = append_blocks(
                container,
                summary_text_block(summary_text),
                has_content=has_content,
            )
        if table_image_url:
            if has_content:
                container.add_item(discord.ui.Separator())
            append_blocks(container, media_block(table_image_url), has_content=False)
            has_content = True
        if has_content:
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

            emoji_val = None
            if button.get("emoji"):
                emoji_val = resolve_button_emoji(button["emoji"])
            elif button.get("icon"):
                emoji_val = icon_for_button(button["icon"])

            item = discord.ui.Button(
                label=button["label"] if button["label"] is not None else "\u200b",
                style=button["style"],
                custom_id=button["id"],
                disabled=button["disabled"],
                url=button["link"],
                emoji=emoji_val,
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
        :return: nothing.
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


class SpectateView(DynamicButtonView):
    """View for status message."""

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
        :param table_image_url: optional attachment:// URL for overview table (same slot as DynamicButtonView).
        """
        buttons = [
            {
                "label": get("buttons.spectate"),
                "style": discord.ButtonStyle.primary,
                "id": spectate_button_id,
                "callback": "none",
                "icon": "spectate",
            },
        ]
        if peek_button_id:
            buttons.append(
                {
                    "label": get("buttons.peek"),
                    "style": discord.ButtonStyle.secondary,
                    "id": peek_button_id,
                    "callback": "none",
                    "icon": "peek",
                },
            )
        buttons.append(
            {
                "label": get("buttons.go_to_game"),
                "style": discord.ButtonStyle.link,
                "link": game_link,
                "icon": "external_link",
            },
        )
        super().__init__(
            buttons,
            summary_text=summary_text,
            table_image_url=table_image_url,
        )


class PageScrubModal(discord.ui.Modal):
    """Modal dialog for scrubbing directly to a specific page number."""

    def __init__(self, current_page: int, max_pages: int, callback_handler) -> None:
        super().__init__(title=get("pagination.modal_title", "Go to Page"))
        self.max_pages = max_pages
        self.callback_handler = callback_handler

        self.page_input = discord.ui.TextInput(
            label=fmt("pagination.modal_label", "Enter page (1-{max})", max=max_pages),
            placeholder=f"Current: {current_page}",
            min_length=1,
            max_length=len(str(max_pages)),
            required=True,
        )
        self.add_item(self.page_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            val = self.page_input.value.strip()
            page = int(val)
            if not (1 <= page <= self.max_pages):
                raise ValueError()
        except ValueError:
            await interaction.response.send_message(
                fmt(
                    "pagination.modal_invalid",
                    "Invalid page number. Please enter a number between 1 and {max}.",
                    max=self.max_pages,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        await self.callback_handler(interaction, page)


class PaginationView(discord.ui.LayoutView):
    """
    Pagination with First/Previous/[Page]/Next/Last (timeout=None).

    Button custom_ids carry only guild_id/user_id for ownership checks;
    page state lives on this view instance. If the view is not registered
    (e.g. after restart), GamesCog.on_interaction replies ephemerally.
    """

    def __init__(
            self,
            guild_id: int,
            user_id: int,
            current_page: int,
            max_pages: int,
            callback_handler,
            body_text: str | None = None,
            media_urls: list[str] | None = None,
    ) -> None:
        """
        :param guild_id: Guild ID for validation (0 if not in a guild)
        :param user_id: User who invoked the command (only they can use the buttons)
        :param current_page: Current page (1-indexed)
        :param max_pages: Total pages
        :param callback_handler: async (interaction, new_page) -> None
        :param media_urls: Optional image URLs (including attachment://) shown above pagination
        """
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self.current_page = current_page
        self.max_pages = max_pages
        self.callback_handler = callback_handler
        container = discord.ui.Container()
        urls = [u for u in (media_urls or []) if u]
        has_content = False
        if urls:
            has_content = append_blocks(
                container,
                media_block(*urls),
                has_content=has_content,
            )
        if body_text:
            if has_content:
                container.add_item(discord.ui.Separator())
            append_blocks(
                container,
                summary_text_block(body_text),
                has_content=True,
            )
            container.add_item(discord.ui.Separator())

        container.add_item(
            pagination_row(
                guild_id=guild_id,
                user_id=user_id,
                current_page=current_page,
                max_pages=max_pages,
                labels={
                    "first": get("buttons.first"),
                    "previous": get("buttons.previous"),
                    "page": "",
                    "next": get("buttons.next"),
                    "last": get("buttons.last"),
                },
                prefixes={
                    "first": BUTTON_PREFIX_PAGINATION_FIRST,
                    "previous": BUTTON_PREFIX_PAGINATION_PREV,
                    "page": BUTTON_PREFIX_PAGINATION_PAGE,
                    "next": BUTTON_PREFIX_PAGINATION_NEXT,
                    "last": BUTTON_PREFIX_PAGINATION_LAST,
                },
                callbacks={
                    "first": self._first_callback,
                    "previous": self._prev_callback,
                    "page": self._page_button_callback,
                    "next": self._next_callback,
                    "last": self._last_callback,
                },
            ),
        )
        self.add_item(container)

    def _validate_interaction(self, interaction: discord.Interaction) -> bool:
        """Validate that the interaction is from the command invoker."""
        if interaction.user.id != self.user_id:
            return False
        return interaction.guild_id == self.guild_id

    async def _first_callback(self, interaction: discord.Interaction) -> None:
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

    async def _page_button_callback(self, interaction: discord.Interaction) -> None:
        """Show page selection modal."""
        if not self._validate_interaction(interaction):
            await response_send_message(
                interaction,
                get("interactions.pagination_not_yours"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        modal = PageScrubModal(
            current_page=self.current_page,
            max_pages=self.max_pages,
            callback_handler=self.callback_handler,
        )
        await interaction.response.send_modal(modal)

    async def _prev_callback(self, interaction: discord.Interaction) -> None:
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

    async def _next_callback(self, interaction: discord.Interaction) -> None:
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

    async def _last_callback(self, interaction: discord.Interaction) -> None:
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
    r"""Rematch button; interaction is handled in GamesCog (see callback \"none\")."""

    def __init__(self, match_id: int, summary_text: str | None = None) -> None:
        super().__init__(
            [
                {
                    "label": get("buttons.rematch"),
                    "style": discord.ButtonStyle.primary,
                    "id": f"{BUTTON_PREFIX_REMATCH}{match_id}",
                    "disabled": False,
                    "callback": "none",
                    "icon": "rematch",
                },
            ],
            summary_text=summary_text,
        )


class QuickActionsView(discord.ui.LayoutView):
    """
    A view with quick action buttons for common operations.
    Can be added to profile, leaderboard, and other embeds.
    """

    def __init__(
            self,
            show_catalog: bool = True,
            show_help: bool = True,
            timeout: int = 180,
    ) -> None:
        super().__init__(timeout=timeout)
        container = discord.ui.Container()
        action_buttons: list[discord.ui.Button] = []
        if show_catalog:
            catalog_btn = primary_button(
                label=get("buttons.view_catalog"),
                custom_id="quick_catalog",
                icon="catalog",
            )
            action_buttons.append(catalog_btn)

        if show_help:
            help_btn = secondary_button(
                label=get("buttons.get_help"),
                custom_id="quick_help",
                icon="about",
            )
            action_buttons.append(help_btn)

        append_blocks(
            container,
            title_block("Quick Actions", icon_key="playcord"),
            has_content=False,
        )
        if action_buttons:
            append_blocks(container, button_row(*action_buttons), has_content=True)
        self.add_item(container)


class CatalogView(discord.ui.LayoutView):
    """
    Board game themed visual catalog view with a filter dropdown select menu and optional pagination.
    """

    def __init__(
            self,
            guild_id: int,
            user_id: int,
            all_games: list[str],
            game_metadata: dict[str, dict],
            games_per_page: int,
            current_page: int = 1,
            active_filter: str | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self.all_games = all_games
        self.game_metadata = game_metadata
        self.games_per_page = games_per_page
        self.active_filter = active_filter
        self.current_page = current_page
        self.max_pages = 1

        self.rebuild_layout()

    def _validate_interaction(self, interaction: discord.Interaction) -> bool:
        """Validate that the interaction is from the command invoker."""
        if interaction.user.id != self.user_id:
            return False
        return interaction.guild_id == self.guild_id

    def rebuild_layout(self) -> None:
        self.clear_items()

        # 1. Filter games based on active_filter (which carries "tag:" or "support:" prefix)
        filtered_games = []
        if self.active_filter and self.active_filter.startswith("tag:"):
            target_tag = self.active_filter[len("tag:"):]
            filtered_games = [
                g for g in self.all_games
                if target_tag in self.game_metadata[g].get("tags", ())
            ]
        elif self.active_filter and self.active_filter.startswith("support:"):
            target_support = self.active_filter[len("support:"):]
            if target_support == "Bots":
                filtered_games = [g for g in self.all_games if self.game_metadata[g].get("supports_bots")]
            elif target_support == "Roles":
                filtered_games = [
                    g for g in self.all_games if (
                            self.game_metadata[g].get("supports_role_selection") or
                            getattr(self.game_metadata[g]["class"].metadata, "role_mode", None) != RoleMode.none or
                            getattr(self.game_metadata[g]["class"].metadata, "role_flow", None) != RoleFlow.none or
                            getattr(self.game_metadata[g]["class"].metadata, "player_roles", None)
                    )
                ]
            elif target_support == "Replays":
                filtered_games = [g for g in self.all_games if self.game_metadata[g].get("supports_replays")]
            elif target_support == "Lobby Options":
                filtered_games = [g for g in self.all_games if self.game_metadata[g].get("supports_lobby_options")]
            else:
                filtered_games = self.all_games
        else:
            filtered_games = self.all_games

        # Sort filtered games alphabetically by name
        display_games = sorted(filtered_games, key=lambda gid: self.game_metadata[gid]["name"])

        # Calculate pages and slice games for the current page
        total_games = len(display_games)
        self.max_pages = max(1, (total_games + self.games_per_page - 1) // self.games_per_page)
        self.current_page = max(1, min(self.current_page, self.max_pages))

        start_idx = (self.current_page - 1) * self.games_per_page
        end_idx = start_idx + self.games_per_page
        page_games = display_games[start_idx:end_idx]

        # 2. Format header and footer
        next_icon = get_icon("forward")

        if self.active_filter:
            category_name = self.active_filter.split(":", 1)[1]
            if self.active_filter.startswith("tag:"):
                header_text = fmt("embeds.catalog.header_format_tag", next_icon=next_icon, category=category_name)
            else:
                header_text = fmt("embeds.catalog.header_format_support", next_icon=next_icon, category=category_name)
        else:
            header_text = fmt("embeds.catalog.header_format_all", next_icon=next_icon)

        # 3. Format game blocks (no > blocks as requested!)
        lines = [f"## {header_text}"]

        space_emoji = get_emoji_string("space")

        difficulty_rating = {
            "Easy": "5/5",
            "Medium": "4/5",
            "Hard": "3/5",
        }

        for game_id in page_games:
            meta = self.game_metadata[game_id]
            game_name = meta["name"]
            game_emoji = get_game_emoji(game_id) or "🎁"
            difficulty = meta.get("difficulty", "Medium")
            rating = difficulty_rating.get(difficulty, "4/5")
            if not rating.endswith("/5"):
                rating = f"{rating}/5"
            playtime = meta.get("time") or "15min"

            # Format player count representation
            allowed = meta.get("class").metadata.player_count
            if isinstance(allowed, int):
                player_count_str = f"{allowed}p"
            elif isinstance(allowed, tuple):
                player_count_str = f"{min(allowed)}-{max(allowed)}p"
            else:
                player_count_str = str(allowed)

            # Retrieve and sort tags alphabetically
            tags_list = sorted(meta.get("tags", ()))
            tags_str = ", ".join(tags_list) or "Board Game"

            # Retrieve and format supported features
            supports = []
            if meta.get("supports_bots"):
                supports.append("Bots")
            if (
                    meta.get("supports_role_selection") or
                    getattr(meta["class"].metadata, "role_mode", None) != RoleMode.none or
                    getattr(meta["class"].metadata, "role_flow", None) != RoleFlow.none or
                    getattr(meta["class"].metadata, "player_roles", None)
            ):
                supports.append("Roles")
            if meta.get("supports_replays"):
                supports.append("Replays")
            if meta.get("supports_lobby_options"):
                supports.append("Lobby Options")
            supports_str = ", ".join(supports) or "None"

            lines.extend([
                f"{game_emoji} **{game_name}**",
                f"{space_emoji} **{rating}** ★ {playtime} `{player_count_str}`",
                f"{space_emoji} *{tags_str}*",
                f"{space_emoji} *Supports: {supports_str}*"
            ])

        body_text = "\n".join(lines)

        # 4. Build Container
        container = discord.ui.Container()
        append_blocks(
            container,
            summary_text_block(body_text),
            has_content=False,
        )
        container.add_item(discord.ui.Separator())

        # 5. Build Select Menu with Dynamic, Sorted Options
        from playcord.infrastructure.constants import NAME
        brand_name = NAME or "PlayCord"
        if self.active_filter:
            category_name = self.active_filter.split(":", 1)[1]
            placeholder = fmt("embeds.catalog.select_placeholder_filter", category=category_name, count=total_games)
        else:
            placeholder = fmt("embeds.catalog.select_placeholder_all", name=brand_name, count=total_games)

        # Collect unique tags from metadata
        all_tags = set()
        for meta in self.game_metadata.values():
            for tag in meta.get("tags", ()):
                all_tags.add(tag)
        sorted_tags = sorted(list(all_tags))

        # Collect support features dynamically
        support_features = set()
        for meta in self.game_metadata.values():
            if meta.get("supports_bots"):
                support_features.add("Bots")
            if (
                    meta.get("supports_role_selection") or
                    getattr(meta["class"].metadata, "role_mode", None) != RoleMode.none or
                    getattr(meta["class"].metadata, "role_flow", None) != RoleFlow.none or
                    getattr(meta["class"].metadata, "player_roles", None)
            ):
                support_features.add("Roles")
            if meta.get("supports_replays"):
                support_features.add("Replays")
            if meta.get("supports_lobby_options"):
                support_features.add("Lobby Options")
        sorted_supports = sorted(list(support_features))

        # Populate options
        select_options = [
            SelectOption(
                label="All Games",
                value="all",
                default=(self.active_filter is None),
                description="Show all games"
            ),
            SelectOption(
                label="\u200b",
                value="header_type",
                description="BY TYPE"
            )
        ]
        for tag in sorted_tags:
            select_options.append(SelectOption(
                label=tag,
                value=f"tag:{tag}",
                default=(self.active_filter == f"tag:{tag}")
            ))

        select_options.append(SelectOption(
            label="\u200b",
            value="header_support",
            description="BY SUPPORT"
        ))
        for sup in sorted_supports:
            select_options.append(SelectOption(
                label=sup,
                value=f"support:{sup}",
                default=(self.active_filter == f"support:{sup}")
            ))

        select = discord.ui.Select(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=select_options,
        )
        select.callback = self._on_select_change

        select_row = discord.ui.ActionRow()
        select_row.add_item(select)
        container.add_item(select_row)

        # 6. Add Pagination Buttons if max_pages > 1
        if self.max_pages > 1:
            container.add_item(discord.ui.Separator())
            container.add_item(
                pagination_row(
                    guild_id=self.guild_id,
                    user_id=self.user_id,
                    current_page=self.current_page,
                    max_pages=self.max_pages,
                    labels={
                        "first": get("buttons.first"),
                        "previous": get("buttons.previous"),
                        "page": "",
                        "next": get("buttons.next"),
                        "last": get("buttons.last"),
                    },
                    prefixes={
                        "first": BUTTON_PREFIX_PAGINATION_FIRST,
                        "previous": BUTTON_PREFIX_PAGINATION_PREV,
                        "page": BUTTON_PREFIX_PAGINATION_PAGE,
                        "next": BUTTON_PREFIX_PAGINATION_NEXT,
                        "last": BUTTON_PREFIX_PAGINATION_LAST,
                    },
                    callbacks={
                        "first": self._first_callback,
                        "previous": self._prev_callback,
                        "page": self._page_button_callback,
                        "next": self._next_callback,
                        "last": self._last_callback,
                    },
                ),
            )

        self.add_item(container)

    async def _first_callback(self, interaction: discord.Interaction) -> None:
        await self._navigate_page(interaction, 1)

    async def _prev_callback(self, interaction: discord.Interaction) -> None:
        await self._navigate_page(interaction, max(1, self.current_page - 1))

    async def _page_button_callback(self, interaction: discord.Interaction) -> None:
        if not self._validate_interaction(interaction):
            await response_send_message(
                interaction,
                get("interactions.pagination_not_yours"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        modal = PageScrubModal(
            current_page=self.current_page,
            max_pages=self.max_pages,
            callback_handler=self._modal_navigate_page,
        )
        await interaction.response.send_modal(modal)

    async def _next_callback(self, interaction: discord.Interaction) -> None:
        await self._navigate_page(interaction, min(self.max_pages, self.current_page + 1))

    async def _last_callback(self, interaction: discord.Interaction) -> None:
        await self._navigate_page(interaction, self.max_pages)

    async def _navigate_page(self, interaction: discord.Interaction, page: int) -> None:
        if not self._validate_interaction(interaction):
            await response_send_message(
                interaction,
                get("interactions.pagination_not_yours"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        self.current_page = page
        await interaction.response.defer()
        self.rebuild_layout()
        await interaction.edit_original_response(view=self)

    async def _modal_navigate_page(self, interaction: discord.Interaction, page: int) -> None:
        self.current_page = page
        self.rebuild_layout()
        await interaction.edit_original_response(view=self)

    async def _on_select_change(self, interaction: discord.Interaction) -> None:
        if not self._validate_interaction(interaction):
            await response_send_message(
                interaction,
                get("interactions.pagination_not_yours"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        # Get selected option
        data = interaction.data if interaction.data is not None else {}
        values = data.get("values")
        selected_value = values[0] if isinstance(values, list) and values else None

        if selected_value in ("header_type", "header_support"):
            await interaction.response.defer()
            await interaction.edit_original_response(view=self)
            return

        if selected_value == "all":
            self.active_filter = None
            self.current_page = 1
        else:
            self.active_filter = selected_value
            self.current_page = 1

        await interaction.response.defer()
        self.rebuild_layout()
        await interaction.edit_original_response(view=self)
