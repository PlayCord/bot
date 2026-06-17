"""Shared layout helpers for PlayCord views built on strife_ui components."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from playcord.display.strife_ui.components import (
    StrifeButton,
    StrifeContainer,
    StrifeDropdown,
)
from playcord.display.strife_ui.emojis import (
    get_emoji_manager,
    resolve_emoji,
    resolve_emoji_string,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


def get_game_emoji(game_id: str) -> str:
    """Resolve a display emoji string for a game key."""
    mgr = get_emoji_manager()
    game_key = f"game_{game_id}"
    if game_key in mgr.emojis:
        return resolve_emoji_string(game_key)
    if game_id in mgr.emojis:
        return resolve_emoji_string(game_id)
    return resolve_emoji_string("playcord")


def icon_for_button(icon_key: str) -> str | discord.PartialEmoji:
    """Resolve an icon key to a button emoji."""
    return resolve_emoji(icon_key)


def icon_for_select_option(icon_key: str) -> str | discord.PartialEmoji:
    """Resolve an icon key to a select-option emoji."""
    return resolve_emoji(icon_key)


def resolve_button_emoji(
    emoji: str | discord.PartialEmoji | discord.Emoji,
) -> str | discord.PartialEmoji | discord.Emoji:
    """Resolve a button emoji from a key, unicode string, or Discord markup."""
    if isinstance(emoji, (discord.PartialEmoji, discord.Emoji)):
        return emoji
    text = str(emoji).strip()
    if text.startswith("<") and text.endswith(">"):
        try:
            return discord.PartialEmoji.from_str(text)
        except ValueError:
            pass
    return resolve_emoji(text)


def format_page_title(title_text: str, *, icon_key: str = "settings") -> str:
    """Format a page title line with a leading icon."""
    emoji_str = resolve_emoji_string(icon_key)
    return f"## {emoji_str} {title_text}"


def primary_button(
    *,
    label: str,
    custom_id: str | None = None,
    icon: str | None = None,
    disabled: bool = False,
    callback: Callable[[discord.Interaction], object] | None = None,
) -> StrifeButton:
    """Create a primary StrifeButton."""
    return StrifeButton(
        label=label,
        emoji=icon or "playcord",
        style=discord.ButtonStyle.primary,
        custom_id=custom_id,
        disabled=disabled,
        callback=callback,
    )


def secondary_button(
    *,
    label: str,
    custom_id: str | None = None,
    icon: str | None = None,
    disabled: bool = False,
    callback: Callable[[discord.Interaction], object] | None = None,
) -> StrifeButton:
    """Create a secondary StrifeButton."""
    return StrifeButton(
        label=label,
        emoji=icon or "settings",
        style=discord.ButtonStyle.secondary,
        custom_id=custom_id,
        disabled=disabled,
        callback=callback,
    )


def link_button(
    *,
    label: str,
    url: str,
    icon: str | None = None,
) -> StrifeButton:
    """Create a link StrifeButton."""
    return StrifeButton(
        label=label,
        emoji=icon or "playcord",
        style=discord.ButtonStyle.link,
        url=url,
    )


def nav_row(*buttons: StrifeButton) -> discord.ui.ActionRow:
    """Pack buttons into a single action row."""
    row = discord.ui.ActionRow()
    for button in buttons:
        row.add_item(button)
    return row


def append_blocks(
    container: StrifeContainer | discord.ui.Container,
    *blocks: discord.ui.Item,
    has_content: bool,
) -> bool:
    """Append one or more layout blocks, inserting separators when needed."""
    for block in blocks:
        if has_content and isinstance(block, discord.ui.ActionRow):
            container.add_item(discord.ui.Separator())
        container.add_item(block)
        has_content = True
    return has_content


def text_block(text: str) -> discord.ui.TextDisplay:
    """Wrap plain text in a TextDisplay."""
    return discord.ui.TextDisplay(text.strip())


def summary_text_block(text: str) -> discord.ui.TextDisplay:
    """Wrap summary text in a TextDisplay."""
    return discord.ui.TextDisplay(text.strip())


def text_sections_block(sections: Sequence[str]) -> discord.ui.TextDisplay:
    """Join multiple text sections into one TextDisplay."""
    return discord.ui.TextDisplay("\n\n".join(s.strip() for s in sections if s.strip()))


def title_block(title: str, *, icon_key: str | None = None) -> discord.ui.TextDisplay:
    """Format a title line with an optional icon."""
    if icon_key:
        emoji_str = resolve_emoji_string(icon_key)
        return discord.ui.TextDisplay(f"### {emoji_str} {title}")
    return discord.ui.TextDisplay(f"### {title}")


def media_block(*urls: str) -> discord.ui.MediaGallery:
    """Build a media gallery from one or more image URLs."""
    gallery = discord.ui.MediaGallery()
    for url in urls:
        if url:
            gallery.add_item(media=url)
    return gallery


def divider() -> discord.ui.Separator:
    """Return a separator component."""
    return discord.ui.Separator()


def button_row(*buttons: StrifeButton | discord.ui.Button) -> discord.ui.ActionRow:
    """Pack arbitrary buttons into an action row."""
    row = discord.ui.ActionRow()
    for button in buttons:
        row.add_item(button)
    return row


def labeled_select(
    description: str,
    select: StrifeDropdown | discord.ui.Select,
    *,
    use_small_text: bool = True,
) -> discord.ui.Item:
    """Return a select; StrifeDropdown carries its own description text."""
    if isinstance(select, StrifeDropdown):
        if description and not select.description_text:
            select.description_text = description.strip()
        return select
    if use_small_text and description.strip():
        return discord.ui.Section(
            discord.ui.TextDisplay(f"-# {description.strip()}"),
            accessory=select,
        )
    return select
