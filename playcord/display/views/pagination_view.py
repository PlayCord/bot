"""Generic pagination LayoutView used by profile, history, and replay fallbacks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord

from playcord.display.strife_ui import (
    StrifeContainer,
    StrifePageScrubModal,
    StrifeView,
    build_pagination_row,
)
from playcord.display.views._layout import (
    append_blocks,
    media_block,
    summary_text_block,
)
from playcord.infrastructure.constants import EPHEMERAL_DELETE_AFTER
from playcord.infrastructure.locale import fmt, get

if TYPE_CHECKING:
    from collections.abc import Callable


async def _response_send_message(
    interaction: discord.Interaction,
    *args: object,
    **kwargs: object,
) -> discord.WebhookMessage:
    return await interaction.response.send_message(*args, **kwargs)  # type: ignore[arg-type]


PageScrubModal = StrifePageScrubModal


class PaginationView(StrifeView):
    """
    Pagination with First/Previous/[Page]/Next/Last (timeout=None).

    Page state lives on this view instance. Strife session routing handles
    expired interactions when the bot restarts or the view is replaced.
    """

    def __init__(
        self,
        guild_id: int,
        user_id: int,
        current_page: int,
        max_pages: int,
        callback_handler: Callable[[discord.Interaction, int], Any],
        body_text: str | None = None,
        media_urls: list[str] | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self.current_page = current_page
        self.max_pages = max_pages
        self.callback_handler = callback_handler
        self.body_text = body_text
        self.media_urls = media_urls
        self.rebuild_layout()

    def rebuild_layout(self) -> None:
        self.clear_items()
        container = StrifeContainer()
        urls = [u for u in (self.media_urls or []) if u]
        has_content = False
        if urls:
            has_content = append_blocks(
                container,
                media_block(*urls),
                has_content=has_content,
            )
        if self.body_text:
            if has_content:
                container.add_item(discord.ui.Separator())
            append_blocks(
                container,
                summary_text_block(self.body_text),
                has_content=True,
            )
            container.add_item(discord.ui.Separator())

        container.add_item(
            build_pagination_row(
                current_page=self.current_page,
                max_pages=self.max_pages,
                first_callback=self._first_callback,
                prev_callback=self._prev_callback,
                page_callback=self._page_button_callback,
                next_callback=self._next_callback,
                last_callback=self._last_callback,
            ),
        )
        self.add_item(container)

    def _validate_interaction(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            return False
        return interaction.guild_id == self.guild_id

    async def _first_callback(self, interaction: discord.Interaction) -> None:
        if not self._validate_interaction(interaction):
            await _response_send_message(
                interaction,
                get("interactions.pagination_not_yours"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        await interaction.response.defer()
        await self.callback_handler(interaction, 1)

    async def _page_button_callback(self, interaction: discord.Interaction) -> None:
        if not self._validate_interaction(interaction):
            await _response_send_message(
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
            title=get("pagination.modal_title", "Go to Page"),
            label=fmt(
                "pagination.modal_label",
                "Enter page (1-{max})",
                max=self.max_pages,
            ),
        )
        await interaction.response.send_modal(modal)

    async def _prev_callback(self, interaction: discord.Interaction) -> None:
        if not self._validate_interaction(interaction):
            await _response_send_message(
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
        if not self._validate_interaction(interaction):
            await _response_send_message(
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
        if not self._validate_interaction(interaction):
            await _response_send_message(
                interaction,
                get("interactions.pagination_not_yours"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        await interaction.response.defer()
        await self.callback_handler(interaction, self.max_pages)
