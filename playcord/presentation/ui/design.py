"""Standardized page layout helpers for borderless PlayCord UI."""

from __future__ import annotations

from datetime import UTC, datetime

import discord

from playcord.infrastructure.constants import NAME, VERSION
from playcord.infrastructure.locale import fmt, get
from playcord.presentation.ui.component_kit import page_title, section_header
from playcord.presentation.ui.containers import CustomContainer


def breadcrumb(*segments: str, separator: str | None = None) -> str:
    """Format navigation breadcrumb: ``Parent > Child``."""
    sep = separator if separator is not None else get("ui.breadcrumb_separator")
    return sep.join(s.strip() for s in segments if s and s.strip())


def bullet_list(items: list[str], *, bullet: str = "•") -> str:
    """Build a standard bullet list from string items."""
    return "\n".join(f"{bullet} {item.strip()}" for item in items if item.strip())


def standard_footer(*, year: int | None = None) -> str:
    """Copyright year, bot name, and version for informational pages."""
    resolved_year = year if year is not None else datetime.now(UTC).year
    return fmt(
        "footer.standard",
        year=resolved_year,
        name=NAME,
        version=VERSION,
    )


def with_footer(
    container: CustomContainer,
    *,
    year: int | None = None,
) -> CustomContainer:
    """Attach the standard informational footer to a container."""
    container.set_footer(text=standard_footer(year=year))
    return container


def page(
    title: str,
    *,
    breadcrumb_trail: str | None = None,
    body: str | None = None,
    color: discord.Color | None = None,
) -> CustomContainer:
    """
    Create a borderless page container with optional breadcrumb and body text.

    The title is rendered as a bold markdown header in the description block.
    """
    parts: list[str] = []
    if breadcrumb_trail:
        parts.append(breadcrumb_trail)
    parts.append(page_title(title))
    if body and body.strip():
        parts.append(body.strip())
    return CustomContainer(
        description="\n\n".join(parts),
        color=color,
    )
