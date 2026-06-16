"""Reusable Discord component builders with unified styling."""

from __future__ import annotations

from collections.abc import Callable

import discord

from playcord.presentation.ui.emojis import (
    ICONS,
    get_icon,
    icon_for_button,
    icon_for_select_option,
)


def primary_button(
    *,
    label: str,
    custom_id: str | None = None,
    icon: str = "play",
    disabled: bool = False,
    callback: Callable | None = None,
) -> discord.ui.Button:
    """Blurple button for main calls to action, active tabs, or confirmations."""
    btn = discord.ui.Button(
        label=label,
        style=discord.ButtonStyle.primary,
        custom_id=custom_id,
        emoji=icon_for_button(icon),
        disabled=disabled,
    )
    if callback is not None:
        btn.callback = callback
    return btn


def secondary_button(
    *,
    label: str,
    custom_id: str | None = None,
    icon: str = "previous",
    disabled: bool = False,
    callback: Callable | None = None,
) -> discord.ui.Button:
    """Gray button for navigation, back actions, and secondary toggles."""
    btn = discord.ui.Button(
        label=label,
        style=discord.ButtonStyle.secondary,
        custom_id=custom_id,
        emoji=icon_for_button(icon),
        disabled=disabled,
    )
    if callback is not None:
        btn.callback = callback
    return btn


def link_button(
    *,
    label: str,
    url: str,
    icon: str = "external_link",
) -> discord.ui.Button:
    """Link button with external-link outline icon."""
    return discord.ui.Button(
        label=label,
        style=discord.ButtonStyle.link,
        url=url,
        emoji=icon_for_button(icon),
    )


def nav_row(*buttons: discord.ui.Button) -> discord.ui.ActionRow:
    """Bottom-most navigation action row."""
    row = discord.ui.ActionRow()
    for button in buttons:
        row.add_item(button)
    return row


def page_title(text: str) -> str:
    """Markdown title for page containers."""
    return f"## {text.strip()}"


def format_page_title(text: str, *, icon_key: str | None = None) -> str:
    """
    Format a TextDisplay heading for containers.

    Discord requires heading markers at the start of the line, so any icon
    is placed after the marker: ``## :emoji: Title``.
    """
    text = text.strip()
    if icon_key:
        icon = get_icon(icon_key)
        if icon:
            return f"## {icon} {text}"
    return f"## {text}"


def section_header(text: str, *, icon_key: str | None = None) -> str:
    """Return large markdown for a section title."""
    return format_page_title(text, icon_key=icon_key)


def small_text(text: str) -> str:
    """Return Discord small-print markdown (TextDisplay ``-#`` prefix)."""
    return f"-# {text.strip()}"


def icon_prefix(icon_key: str, text: str) -> str:
    """Prefix message text with a custom icon when available."""
    icon = getattr(ICONS, icon_key, "")
    if icon:
        return f"{icon} {text}"
    return text
