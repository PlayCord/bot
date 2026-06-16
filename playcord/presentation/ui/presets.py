"""Composable UI preset blocks for icon-forward LayoutView pages."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import discord

from playcord.presentation.ui.component_kit import (
    format_page_title,
    icon_prefix,
    nav_row,
    section_header,
    small_text,
)
from playcord.presentation.ui.containers import (
    TEXT_DISPLAY_MAX,
    _add_text_sections,
    chunk_text_display_lines,
)


@dataclass(slots=True)
class UIViewBlock:
    """One logical block appended to a LayoutView container."""

    apply: Callable[[discord.ui.Container], None]
    separator_before: bool = True


def title_block(text: str, *, icon_key: str | None = None) -> UIViewBlock:
    """Page title (``## :icon: Title``)."""

    def _apply(container: discord.ui.Container) -> None:
        container.add_item(
            discord.ui.TextDisplay(format_page_title(text, icon_key=icon_key)),
        )

    return UIViewBlock(apply=_apply, separator_before=False)


def text_block(markdown: str) -> UIViewBlock:
    """Plain markdown body text."""

    def _apply(container: discord.ui.Container) -> None:
        text = (markdown or "").strip()
        if not text:
            return
        for chunk in chunk_text_display_lines(text):
            container.add_item(discord.ui.TextDisplay(chunk))

    return UIViewBlock(apply=_apply)


def section_block(
    header: str,
    body: str,
    *,
    icon_key: str | None = None,
) -> UIViewBlock:
    """Section with icon-prefixed header and body."""

    def _apply(container: discord.ui.Container) -> None:
        parts = [section_header(header, icon_key=icon_key)]
        body_text = (body or "").strip()
        if body_text:
            parts.append(body_text)
        _add_text_sections(container, ["\n".join(parts)])

    return UIViewBlock(apply=_apply)


def badge_line(*items: tuple[str, str]) -> UIViewBlock:
    """
    Icon-prefixed inline badges.

    Each item is ``(icon_key, label)`` e.g. ``("creator", "Creator")``.
    """

    def _apply(container: discord.ui.Container) -> None:
        parts = [icon_prefix(key, label) for key, label in items if label.strip()]
        if parts:
            container.add_item(discord.ui.TextDisplay(" ".join(parts)))

    return UIViewBlock(apply=_apply)


def labeled_select(
    description: str,
    select: discord.ui.Select,
    *,
    use_small_text: bool = True,
) -> UIViewBlock:
    """Description above a dropdown (lobby settings pattern)."""

    def _apply(container: discord.ui.Container) -> None:
        desc = (description or "").strip()
        if desc:
            display = small_text(desc) if use_small_text else desc
            container.add_item(discord.ui.TextDisplay(display))
        row = discord.ui.ActionRow()
        row.add_item(select)
        container.add_item(row)

    return UIViewBlock(apply=_apply)


def button_row(*buttons: discord.ui.Button) -> UIViewBlock:
    """Action row of icon-bearing buttons."""

    def _apply(container: discord.ui.Container) -> None:
        if not buttons:
            return
        container.add_item(nav_row(*buttons))

    return UIViewBlock(apply=_apply)


def media_block(*urls: str) -> UIViewBlock:
    """Media gallery for one or more image URLs."""

    def _apply(container: discord.ui.Container) -> None:
        resolved = [u for u in urls if u]
        if not resolved:
            return
        items = [discord.MediaGalleryItem(url) for url in resolved]
        container.add_item(discord.ui.MediaGallery(*items))

    return UIViewBlock(apply=_apply)


def footer_block(text: str) -> UIViewBlock:
    """Small footer line at the bottom of a view."""

    def _apply(container: discord.ui.Container) -> None:
        footer = (text or "").strip()
        if footer:
            container.add_item(discord.ui.TextDisplay(small_text(footer)))

    return UIViewBlock(apply=_apply)


def divider() -> UIViewBlock:
    """Visible separator between major sections."""

    def _apply(container: discord.ui.Container) -> None:
        container.add_item(discord.ui.Separator())

    return UIViewBlock(apply=_apply, separator_before=False)


def raw_items(*items: discord.ui.Item) -> UIViewBlock:
    """Pre-built discord.ui items (ActionRow, Select row, etc.)."""

    def _apply(container: discord.ui.Container) -> None:
        for item in items:
            container.add_item(item)

    return UIViewBlock(apply=_apply)


def compose_view(
    *blocks: UIViewBlock,
    accent_color: discord.Color | int | None = None,
    timeout: float | None = None,
) -> discord.ui.LayoutView:
    """Assemble blocks into a single LayoutView with consistent separators."""
    view = discord.ui.LayoutView(timeout=timeout)
    container = discord.ui.Container(accent_color=accent_color)
    has_content = False
    for block in blocks:
        if block.separator_before and has_content:
            container.add_item(discord.ui.Separator())
        block.apply(container)
        has_content = True
    view.add_item(container)
    return view


def append_blocks(
    container: discord.ui.Container,
    *blocks: UIViewBlock,
    has_content: bool = False,
) -> bool:
    """
    Append preset blocks to an existing container.

    Returns whether the container now has content (for chaining).
    """
    for block in blocks:
        if block.separator_before and has_content:
            container.add_item(discord.ui.Separator())
        block.apply(container)
        has_content = True
    return has_content


def text_sections_block(sections: list[str]) -> UIViewBlock:
    """Multiple text sections with invisible separators (matchmaking lobby)."""

    def _apply(container: discord.ui.Container) -> None:
        _add_text_sections(container, sections)

    return UIViewBlock(apply=_apply, separator_before=False)


def summary_text_block(summary_text: str) -> UIViewBlock:
    """Single summary line capped at TextDisplay max."""

    def _apply(container: discord.ui.Container) -> None:
        text = (summary_text or "").strip()
        if text:
            container.add_item(discord.ui.TextDisplay(summary_text[:TEXT_DISPLAY_MAX]))

    return UIViewBlock(apply=_apply, separator_before=False)
