"""Presentation-layer chart rendering for analytics (keeps infra free of UI deps)."""

from __future__ import annotations

import io
from typing import Any

from playcord.infrastructure.locale import fmt, get
from playcord.infrastructure.logging import get_logger
from playcord.presentation.ui.graphics.graphs import generate_analytics_summary_chart

log = get_logger("presentation.analytics_charts")


def render_analytics_matplotlib_summary(
    event_counts: list[dict[str, Any]],
    game_counts: list[dict[str, Any]],
    hours: int,
) -> io.BytesIO | None:
    """Owner-facing matplotlib figure (event types vs games).
    Returns ``None`` if there is nothing to plot or rendering fails.
    """
    try:
        return generate_analytics_summary_chart(
            event_counts,
            game_counts,
            suptitle=fmt("commands.analytics.chart_suptitle", hours=hours),
            title_events=get("commands.analytics.chart_events_title"),
            title_games=get("commands.analytics.chart_games_title"),
            empty_panel=get("commands.analytics.chart_empty_panel"),
            xlabel_count=get("commands.analytics.chart_xlabel_count"),
        )
    except Exception as e:
        log.warning("Analytics matplotlib render failed: %s", e, exc_info=True)
        return None
