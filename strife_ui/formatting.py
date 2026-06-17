"""Indented list formatting utilities for strife_ui."""

from __future__ import annotations

from typing import TYPE_CHECKING

from strife_ui.emojis import resolve_emoji_string

if TYPE_CHECKING:
    import discord


class StrifeListItem:
    """Represents an item in an indented strife list display."""

    def __init__(
        self,
        *,
        title: str,
        emoji: str | int | discord.Emoji | discord.PartialEmoji,
        details: list[str] | None = None,
    ) -> None:
        """
        Initialize a StrifeListItem.

        Raises:
            ValueError: If no emoji is provided.

        """
        if not emoji:
            err_msg = "Every StrifeListItem must have an emoji."
            raise ValueError(err_msg)

        self.title = title.strip()
        self.emoji = emoji
        self.details = details or []


def format_list_items(
    items: list[StrifeListItem],
    *,
    space_emoji: str | int | discord.Emoji | discord.PartialEmoji,
) -> str:
    """
    Format a list of StrifeListItems into an indented, professional display.

    Requires a custom space emoji.
    """
    if not space_emoji:
        err_msg = (
            "strife_ui format_list_items requires a custom "
            "space_emoji to format indentation."
        )
        raise ValueError(err_msg)

    space_str = resolve_emoji_string(space_emoji)
    lines: list[str] = []

    for item in items:
        emoji_str = resolve_emoji_string(item.emoji)
        lines.append(f"{emoji_str} **{item.title}**")
        lines.extend(f"{space_str} {detail.strip()}" for detail in item.details)

    return "\n".join(lines)
