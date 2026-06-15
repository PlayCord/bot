"""Graph generation utilities for PlayCord bot using matplotlib."""

import io
from typing import Any

import matplotlib as mpl

mpl.use("Agg")  # Non-interactive backend for Discord bot
import matplotlib.pyplot as plt


def generate_analytics_summary_chart(
    event_counts: list[dict[str, Any]],
    game_counts: list[dict[str, Any]],
    *,
    suptitle: str,
    title_events: str,
    title_games: str,
    empty_panel: str,
    xlabel_count: str = "Count",
    max_rows: int = 22,
    figsize: tuple[float, float] = (12, 6.2),
    dpi: int = 100,
) -> io.BytesIO | None:
    """
    Two horizontal bar charts: analytics rows by ``event_type`` and by game slug (``game_type`` key).

    Returns ``None`` when both input lists are empty (nothing to plot).
    """
    if not event_counts and not game_counts:
        return None

    def panel(
        ax,
        rows: list[dict[str, Any]],
        label_key: str,
        value_key: str,
        title: str,
        bar_color: str,
    ) -> None:
        if not rows:
            ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
            ax.axis("off")
            ax.text(
                0.5,
                0.5,
                empty_panel,
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=11,
                color="#666666",
            )
            return
        slice_rows = rows[:max_rows]
        labels = [str(r.get(label_key) or "?")[:44] for r in slice_rows]
        vals = [int(r[value_key]) for r in slice_rows]
        labels.reverse()
        vals.reverse()
        y = list(range(len(labels)))
        ax.barh(y, vals, color=bar_color, height=0.62, edgecolor="white", linewidth=0.5)
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=9)
        ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
        ax.set_xlabel(xlabel_count, fontsize=10)
        ax.grid(True, axis="x", alpha=0.35, linestyle="--", linewidth=0.8)
        ax.set_axisbelow(True)

    fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=figsize, dpi=dpi)
    fig.patch.set_facecolor("white")
    panel(ax_l, event_counts, "event_type", "cnt", title_events, "#6877ED")
    panel(ax_r, game_counts, "game_type", "cnt", title_games, "#57F287")
    fig.suptitle(suptitle, fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout(rect=(0, 0, 1, 0.94))

    buffer = io.BytesIO()
    fig.savefig(
        buffer,
        format="png",
        bbox_inches="tight",
        facecolor="white",
        edgecolor="none",
    )
    plt.close(fig)
    buffer.seek(0)
    return buffer
