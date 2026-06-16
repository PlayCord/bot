"""Backward-compatible re-exports from playcord.ui.components and playcord.ui.text."""

from playcord.ui.components import (
    link_button,
    nav_row,
    primary_button,
    secondary_button,
)
from playcord.ui.emojis import icon_for_button, icon_for_select_option
from playcord.ui.text import (
    format_page_title,
    icon_prefix,
    page_title,
    section_header,
    small_text,
)

__all__ = [
    "format_page_title",
    "icon_for_button",
    "icon_for_select_option",
    "icon_prefix",
    "link_button",
    "nav_row",
    "page_title",
    "primary_button",
    "secondary_button",
    "section_header",
    "small_text",
]
