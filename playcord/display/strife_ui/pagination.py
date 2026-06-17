"""Pagination components, row layouts, and scrubbing modals for strife_ui."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord

from playcord.display.strife_ui.components import StrifeButton, StrifeContainer
from playcord.display.strife_ui.emojis import get_emoji_manager, resolve_emoji_string
from playcord.display.strife_ui.routing import StrifeView

if TYPE_CHECKING:
    from collections.abc import Callable


class StrifePageScrubModal(discord.ui.Modal):
    """Modal dialog for scrubbing directly to a specific page number."""

    def __init__(
        self,
        *,
        current_page: int,
        max_pages: int,
        callback_handler: Callable[[discord.Interaction, int], Any],
        title: str = "Go to Page",
        label: str | None = None,
    ) -> None:
        """Initialize a StrifePageScrubModal."""
        super().__init__(title=title)
        self.max_pages = max_pages
        self.callback_handler = callback_handler

        input_label = label or f"Enter page (1-{max_pages})"
        self.page_input = discord.ui.TextInput(
            label=input_label,
            placeholder=f"Current: {current_page}",
            min_length=1,
            max_length=len(str(max_pages)),
            required=True,
        )
        self.add_item(self.page_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Process page jump input validation and trigger callback."""
        val = self.page_input.value.strip()
        if not val.isdigit() or not (1 <= int(val) <= self.max_pages):
            err_msg = (
                "Invalid page number. "
                f"Please enter a number between 1 and {self.max_pages}."
            )
            await interaction.response.send_message(err_msg, ephemeral=True)
            return

        page = int(val)
        await interaction.response.defer()
        await self.callback_handler(interaction, page)


def build_pagination_row(  # noqa: PLR0913
    *,
    current_page: int,
    max_pages: int,
    first_callback: Callable[[discord.Interaction], Any],
    prev_callback: Callable[[discord.Interaction], Any],
    page_callback: Callable[[discord.Interaction], Any],
    next_callback: Callable[[discord.Interaction], Any],
    last_callback: Callable[[discord.Interaction], Any],
    first_emoji: Any = None,  # noqa: ANN401
    prev_emoji: Any = None,  # noqa: ANN401
    page_emoji: Any = None,  # noqa: ANN401
    next_emoji: Any = None,  # noqa: ANN401
    last_emoji: Any = None,  # noqa: ANN401
) -> discord.ui.ActionRow:
    """Build a Components v2 ActionRow populated with 5 pagination buttons."""
    # Resolve emojis with fallback values
    mgr = get_emoji_manager()

    emoji_first = first_emoji or (
        resolve_emoji_string("first") if "first" in mgr.emojis else "⏪"
    )
    emoji_prev = prev_emoji or (
        resolve_emoji_string("previous") if "previous" in mgr.emojis else "◀️"
    )
    emoji_page = page_emoji or (
        resolve_emoji_string("page") if "page" in mgr.emojis else "🔍"
    )
    emoji_next = next_emoji or (
        resolve_emoji_string("next") if "next" in mgr.emojis else "▶️"
    )
    emoji_last = last_emoji or (
        resolve_emoji_string("last") if "last" in mgr.emojis else "⏩"
    )

    row = discord.ui.ActionRow()

    # Add First
    row.add_item(
        StrifeButton(
            label="",
            emoji=emoji_first,
            disabled=current_page <= 1,
            callback=first_callback,
        )
    )
    # Add Prev
    row.add_item(
        StrifeButton(
            label="",
            emoji=emoji_prev,
            disabled=current_page <= 1,
            callback=prev_callback,
        )
    )
    # Add Page Indicator / Scrub Trigger
    row.add_item(
        StrifeButton(
            label=f"{current_page} / {max_pages}",
            emoji=emoji_page,
            disabled=max_pages <= 1,
            callback=page_callback,
        )
    )
    # Add Next
    row.add_item(
        StrifeButton(
            label="",
            emoji=emoji_next,
            disabled=current_page >= max_pages,
            callback=next_callback,
        )
    )
    # Add Last
    row.add_item(
        StrifeButton(
            label="",
            emoji=emoji_last,
            disabled=current_page >= max_pages,
            callback=last_callback,
        )
    )

    return row


class StrifePaginationView(StrifeView):
    """A StrifeView that manages pagination navigation using Components v2."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        current_page: int,
        max_pages: int,
        callback_handler: Callable[[discord.Interaction, int], Any],
        user_id: int | None = None,
        body_text: str | None = None,
        first_emoji: Any = None,  # noqa: ANN401
        prev_emoji: Any = None,  # noqa: ANN401
        page_emoji: Any = None,  # noqa: ANN401
        next_emoji: Any = None,  # noqa: ANN401
        last_emoji: Any = None,  # noqa: ANN401
        timeout: float | None = 180.0,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize a StrifePaginationView."""
        super().__init__(timeout=timeout, **kwargs)
        self.current_page = current_page
        self.max_pages = max_pages
        self.callback_handler = callback_handler
        self.user_id = user_id
        self.body_text = body_text

        self.first_emoji = first_emoji
        self.prev_emoji = prev_emoji
        self.page_emoji = page_emoji
        self.next_emoji = next_emoji
        self.last_emoji = last_emoji

        self.rebuild_layout()

    def rebuild_layout(self) -> None:
        """Construct the view layout using ContainerClass if available."""
        self.clear_items()

        container = StrifeContainer()
        has_content = False

        if self.body_text:
            body_clean = self.body_text.strip()
            if body_clean:
                container.add_item(discord.ui.TextDisplay(body_clean))
                has_content = True

        # Build pagination action row
        p_row = build_pagination_row(
            current_page=self.current_page,
            max_pages=self.max_pages,
            first_callback=self._first_callback,
            prev_callback=self._prev_callback,
            page_callback=self._page_callback,
            next_callback=self._next_callback,
            last_callback=self._last_callback,
            first_emoji=self.first_emoji,
            prev_emoji=self.prev_emoji,
            page_emoji=self.page_emoji,
            next_emoji=self.next_emoji,
            last_emoji=self.last_emoji,
        )

        if has_content:
            container.add_item(discord.ui.Separator())

        container.add_item(p_row)
        self.add_item(container)

    def get_current_payload(self) -> dict[str, Any]:
        """Compile the Discord message payload for the current pagination state."""
        return {
            "content": "",
            "view": self,
        }

    async def _navigate_to(self, interaction: discord.Interaction, page: int) -> None:
        """Update current page and trigger navigation callback."""
        self.current_page = page
        self.rebuild_layout()
        await self.callback_handler(interaction, page)

    async def _first_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self._navigate_to(interaction, 1)

    async def _prev_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self._navigate_to(interaction, max(1, self.current_page - 1))

    async def _page_callback(self, interaction: discord.Interaction) -> None:
        modal = StrifePageScrubModal(
            current_page=self.current_page,
            max_pages=self.max_pages,
            callback_handler=self._modal_callback_handler,
        )
        await interaction.response.send_modal(modal)

    async def _modal_callback_handler(
        self, interaction: discord.Interaction, page: int
    ) -> None:
        # Modal handles the defer/edit inside on_submit, we just update local state
        await self._navigate_to(interaction, page)

    async def _next_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self._navigate_to(interaction, min(self.max_pages, self.current_page + 1))

    async def _last_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self._navigate_to(interaction, self.max_pages)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Verify the user is allowed to navigate this pagination view."""
        if self.user_id is not None and interaction.user.id != self.user_id:
            msg = "This menu belongs to someone else."
            await interaction.response.send_message(msg, ephemeral=True)
            return False

        return await super().interaction_check(interaction)
