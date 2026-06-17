"""Screen navigation system with breadcrumbs and nested menu layouts."""

from __future__ import annotations

import logging
from typing import Any

import discord

from strife_ui.components import StrifeButton, StrifeDropdown
from strife_ui.emojis import get_emoji_manager, resolve_emoji_string
from strife_ui.routing import StrifeView

logger = logging.getLogger("strife_ui.screens")


class StrifeScreen:
    """Represents a single UI screen state."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        title: str,
        emoji: str | int | discord.Emoji | discord.PartialEmoji,
        description: str = "",
        embed: discord.Embed | None = None,
        items: list[discord.ui.Item] | None = None,
        ephemeral: bool = False,
        disable_back: bool = False,
    ) -> None:
        """
        Initialize a StrifeScreen.

        Raises:
            ValueError: If no emoji is provided.

        """
        if not emoji:
            err_msg = "StrifeScreen requires an emoji."
            raise ValueError(err_msg)

        self.title = title.strip()
        self.emoji = emoji
        self.description = description.strip()
        self.embed = embed
        self.items = items or []
        self.ephemeral = ephemeral
        self.disable_back = disable_back


class StrifeNavigator(StrifeView):
    """A StrifeView that manages a stack of StrifeScreens with breadcrumbs."""

    def __init__(
        self,
        root_screen: StrifeScreen,
        *,
        user_id: int | None = None,
        interaction_id: str | None = None,
        timeout: float | None = 180.0,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize a StrifeNavigator."""
        super().__init__(interaction_id=interaction_id, timeout=timeout, **kwargs)
        self.user_id = user_id
        self.screen_stack: list[StrifeScreen] = [root_screen]
        self.rebuild_layout()

    def get_breadcrumb_header(self) -> str:
        """Construct breadcrumb header for current navigation stack."""
        parts: list[str] = []
        for screen in self.screen_stack:
            emoji_str = resolve_emoji_string(screen.emoji)
            parts.append(f"{emoji_str} {screen.title}")

        arrow = "➡️"
        mgr = get_emoji_manager()
        if "forward" in mgr.emojis:
            arrow = resolve_emoji_string("forward")

        joined = f" {arrow} ".join(parts)
        return f"## {joined}"

    def get_current_payload(self) -> dict[str, Any]:
        """Compile the Discord message payload for the current screen."""
        current_screen = self.screen_stack[-1]
        breadcrumb = self.get_breadcrumb_header()

        # Build dropdown subtext descriptions using a list comprehension
        dropdown_subtexts = [
            f"-# {child.description_text}"
            for child in self.walk_children()
            if isinstance(child, StrifeDropdown) and child.description_text
        ]

        content_parts: list[str] = [breadcrumb]
        if current_screen.description:
            content_parts.append(current_screen.description)
        if dropdown_subtexts:
            content_parts.append("\n".join(dropdown_subtexts))

        return {
            "content": "\n\n".join(content_parts),
            "embed": current_screen.embed,
            "view": self,
        }

    def rebuild_layout(self) -> None:
        """Clear components and build layout for the current active screen."""
        self.clear_items()
        current_screen = self.screen_stack[-1]

        is_nested = len(self.screen_stack) > 1
        no_back = current_screen.disable_back or current_screen.ephemeral

        container = discord.ui.Container()

        if is_nested and not no_back:
            back_emoji = "⬅️"
            mgr = get_emoji_manager()
            if "previous" in mgr.emojis:
                back_emoji = resolve_emoji_string("previous")

            back_btn = StrifeButton(
                label="Back",
                emoji=back_emoji,
                style=discord.ButtonStyle.secondary,
                callback=self._back_button_callback,
            )
            container.add_item(back_btn)

        for item in current_screen.items:
            container.add_item(item)

        self.add_item(container)

    async def _back_button_callback(self, interaction: discord.Interaction) -> None:
        await self.back(interaction)

    async def back(self, interaction: discord.Interaction) -> None:
        """Navigate back to the previous screen."""
        if len(self.screen_stack) > 1:
            self.screen_stack.pop()
            self.rebuild_layout()
            payload = self.get_current_payload()
            if not interaction.response.is_done():
                await interaction.response.edit_message(**payload)
            else:
                await interaction.message.edit(**payload)

    async def transition_to(
        self, interaction: discord.Interaction, screen: StrifeScreen
    ) -> None:
        """Transition to a new screen. Spawns ephemeral message if flagged."""
        if screen.ephemeral:
            # Ephemeral screen: open as a new, ephemeral navigator session
            sub_navigator = StrifeNavigator(
                screen,
                user_id=self.user_id,
                interaction_id=self.interaction_id,
                timeout=self.timeout,
            )
            payload = sub_navigator.get_current_payload()
            await interaction.response.send_message(**payload, ephemeral=True)
            return

        self.screen_stack.append(screen)
        self.rebuild_layout()
        payload = self.get_current_payload()

        if not interaction.response.is_done():
            await interaction.response.edit_message(**payload)
        else:
            await interaction.message.edit(**payload)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if invoker user ID matches active user permission."""
        if self.user_id is not None and interaction.user.id != self.user_id:
            msg = "This menu belongs to someone else."
            await interaction.response.send_message(msg, ephemeral=True)
            return False

        # Delegate to routing verification
        return await super().interaction_check(interaction)
