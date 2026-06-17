"""Per-command Discord views that render logic-layer results into UI."""

from __future__ import annotations

from playcord.display.views.about_command import AboutView, AttributionsView
from playcord.display.views.catalog_command import CatalogView
from playcord.display.views.dynamic_views import (
    DynamicButtonView,
    QuickActionsView,
    RematchView,
    SpectateView,
)
from playcord.display.views.matchmaking_lobby import (
    LobbySettingsView,
    MatchmakingLobbyView,
)
from playcord.display.views.pagination_view import PageScrubModal, PaginationView
from playcord.display.views.replay_viewer import ReplayViewerView

__all__ = [
    "AboutView",
    "AttributionsView",
    "CatalogView",
    "DynamicButtonView",
    "LobbySettingsView",
    "MatchmakingLobbyView",
    "PageScrubModal",
    "PaginationView",
    "QuickActionsView",
    "RematchView",
    "ReplayViewerView",
    "SpectateView",
]
