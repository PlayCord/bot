"""Rich formatting helpers for slash-command responses."""

from __future__ import annotations

from typing import Any

from playcord.infrastructure.locale import get


def format_feature_badges(
    *,
    supports_role_selection: bool,
    supports_replays: bool,
    supports_bots: bool,
    supports_lobby_options: bool,
) -> str:
    """Compact feature line with emoji badges."""
    badges: list[str] = []
    if supports_role_selection:
        badges.append(get("display.features.roles"))
    if supports_replays:
        badges.append(get("display.features.replays"))
    if supports_bots:
        badges.append(get("display.features.bots"))
    if supports_lobby_options:
        badges.append(get("display.features.options"))
    if not badges:
        return get("display.features.none")
    return " · ".join(badges)


def format_match_outcome(outcome: str) -> str:
    """Prefix match outcomes with a small visual indicator."""
    text = (outcome or "").strip()
    lower = text.lower()
    if not text:
        return get("display.outcome.unknown")
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
    return get(f"display.outcome.{kind}").replace("{outcome}", text)


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
