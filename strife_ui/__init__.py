"""strife_ui: An opinionated discord.py UI library."""

from __future__ import annotations

from strife_ui.components import (
    StrifeButton,
    StrifeDropdown,
    StrifeSelectCategory,
    StrifeSelectOption,
)
from strife_ui.emojis import (
    get_emoji_manager,
    resolve_emoji,
    resolve_emoji_string,
    set_emoji_cache_path,
)
from strife_ui.formatting import StrifeListItem, format_list_items
from strife_ui.pagination import (
    StrifePageScrubModal,
    StrifePaginationView,
    build_pagination_row,
)
from strife_ui.routing import (
    StrifeRegistry,
    StrifeView,
    check_strife_interaction,
    generate_interaction_id,
    setup_strife_middleware,
)
from strife_ui.screens import StrifeNavigator, StrifeScreen

__all__ = [
    "StrifeButton",
    "StrifeDropdown",
    "StrifeListItem",
    "StrifeNavigator",
    "StrifePageScrubModal",
    "StrifePaginationView",
    "StrifeRegistry",
    "StrifeScreen",
    "StrifeSelectCategory",
    "StrifeSelectOption",
    "StrifeView",
    "build_pagination_row",
    "check_strife_interaction",
    "format_list_items",
    "generate_interaction_id",
    "get_emoji_manager",
    "resolve_emoji",
    "resolve_emoji_string",
    "set_emoji_cache_path",
    "setup_strife_middleware",
]
