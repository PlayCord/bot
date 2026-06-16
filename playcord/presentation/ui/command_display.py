"""Rich formatting helpers for slash-command responses."""

from __future__ import annotations

from typing import Any

from playcord.infrastructure.locale import get
from playcord.presentation.ui.component_kit import icon_prefix

_OUTCOME_ICON_KEYS: dict[str, str] = {
    "win": "win",
    "loss": "loss",
    "draw": "draw",
    "interrupted": "interrupted",
    "default": "success",
}

_STATUS_ICON_KEYS: dict[str, str] = {
    "status_completed": "success",
    "status_interrupted": "interrupted",
    "status_abandoned": "abandoned",
}


def format_feature_badges(
    *,
    supports_role_selection: bool,
    supports_replays: bool,
    supports_bots: bool,
    supports_lobby_options: bool,
) -> str:
    """Compact feature line with custom icon badges."""
    badges: list[str] = []
    if supports_role_selection:
        badges.append(
            icon_prefix("roles", get("display.features.roles")),
        )
    if supports_replays:
        badges.append(
            icon_prefix("replay", get("display.features.replays")),
        )
    if supports_bots:
        badges.append(
            icon_prefix("bot", get("display.features.bots")),
        )
    if supports_lobby_options:
        badges.append(
            icon_prefix("options", get("display.features.options")),
        )
    if not badges:
        return get("display.features.none")
    return " · ".join(badges)


def format_match_outcome(outcome: str) -> str:
    """Prefix match outcomes with a custom icon when available."""
    text = (outcome or "").strip()
    lower = text.lower()
    if not text:
        return icon_prefix("info", get("display.outcome.unknown"))
    if "win" in lower:
        return fmt_outcome("win", text)
    if "loss" in lower or "lost" in lower:
        return fmt_outcome("loss", text)
    if "draw" in lower:
        return fmt_outcome("draw", text)
    if "interrupt" in lower or "abandon" in lower:
        return fmt_outcome("interrupted", text)
    return fmt_outcome("default", text)


def fmt_outcome(kind: str, text: str) -> str:
    icon_key = _OUTCOME_ICON_KEYS.get(kind, "success")
    return icon_prefix(icon_key, text)


def format_history_status(status_key: str) -> str:
    """Format a history status label with its manifest icon."""
    label = get(f"display.history.{status_key}")
    icon_key = _STATUS_ICON_KEYS.get(status_key, "info")
    return icon_prefix(icon_key, label)


def format_history_line(
    *,
    match_id: str,
    game_key: str,
    rank_text: str,
    player_count: Any,
    status_label: str,
    summary: str | None,
) -> str:
    base = get("display.history.line_format").format(
        match_id=match_id,
        game_key=game_key,
        rank=rank_text,
        count=player_count,
        status=status_label,
    )
    if summary:
        return f"{base} — {format_match_outcome(summary)}"
    return base
