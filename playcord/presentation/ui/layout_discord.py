"""Discord LayoutView and dynamic button views."""

from __future__ import annotations

from typing import Any

import discord

from playcord.infrastructure.constants import (
    BUTTON_PREFIX_PAGINATION_FIRST,
    BUTTON_PREFIX_PAGINATION_LAST,
    BUTTON_PREFIX_PAGINATION_NEXT,
    BUTTON_PREFIX_PAGINATION_PREV,
    BUTTON_PREFIX_REMATCH,
    EPHEMERAL_DELETE_AFTER,
)
from playcord.infrastructure.locale import get
from playcord.presentation.ui.containers import (
    TEXT_DISPLAY_MAX,
)


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


class DynamicButtonView(discord.ui.LayoutView):
    """Dynamic button view: this is PAIN."""

    def __init__(
        self,
        buttons: list[dict],
        summary_text: str | None = None,
        table_image_url: str | None = None,
    ) -> None:
        """Create a dynamic button view
        :param buttons: list of buttons as dictionaries
        look at class D.
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
                ),
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
                # Discord requires a label or emoji. If callers omit a label
                # provide a  zero-width space so the component is valid
                # but visually empty.
                label=button["label"] if button["label"] is not None else "\u200b",
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
        """If a "dead" view is interacted, simply disable each component and update the message
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


class MatchmakingView(DynamicButtonView):
    """View for matchmaking message."""

    def __init__(
        self,
        join_button_id=None,
        leave_button_id=None,
        ready_button_id=None,
        ready_button_label: str | None = None,
        summary_text: str | None = None,
        table_image_url: str | None = None,
    ) -> None:
        """Create a matchmaking view (Join / Leave / optional Ready — no Start; game begins when all ready)."""
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
                },
            )
        super().__init__(
            buttons,
            summary_text=summary_text,
            table_image_url=table_image_url,
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
        """Create a spectate view
        :param spectate_button_id: custom ID of the spectate button
        :param peek_button_id: custom ID of the peek button
        :param game_link: the link to the game
        :param table_image_url: optional attachment:// URL for overview table (same slot as DynamicButtonView).
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
                },
            )
        buttons.append(
            {
                "label": get("buttons.go_to_game"),
                "style": discord.ButtonStyle.gray,
                "link": game_link,
            },
        )
        super().__init__(
            buttons,
            summary_text=summary_text,
            table_image_url=table_image_url,
        )


class PaginationView(discord.ui.LayoutView):
    """Pagination with First/Previous/Next/Last (timeout=None).

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
    ) -> None:
        """:param guild_id: Guild ID for validation (0 if not in a guild)
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
                    "style": discord.ButtonStyle.success,
                    "id": f"{BUTTON_PREFIX_REMATCH}{match_id}",
                    "disabled": False,
                    "callback": "none",
                },
            ],
            summary_text=summary_text,
        )


class QuickActionsView(discord.ui.LayoutView):
    """A view with quick action buttons for common operations.
    Can be added to profile, leaderboard, and other embeds.
    """

    def __init__(
        self,
        show_catalog: bool = True,
        show_help: bool = True,
        timeout: int = 180,
    ) -> None:
        super().__init__(timeout=timeout)
        container = discord.ui.Container(discord.ui.TextDisplay("### Quick Actions"))
        row = discord.ui.ActionRow()
        if show_catalog:
            row.add_item(
                discord.ui.Button(
                    label=get("buttons.view_catalog"),
                    style=discord.ButtonStyle.primary,
                    custom_id="quick_catalog",
                ),
            )

        if show_help:
            row.add_item(
                discord.ui.Button(
                    label=get("buttons.get_help"),
                    style=discord.ButtonStyle.secondary,
                    custom_id="quick_help",
                ),
            )
        container.add_item(row)
        self.add_item(container)
