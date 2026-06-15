"""Shared helpers for PlayCord game implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playcord.api import GameInput
    from playcord.core.player import Player


def parse_player_id(raw: object) -> int | None:
    text = str(raw).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    return int(digits)


def player_from_input(
    result: GameInput,
    players: list[Player],
) -> Player | None:
    raw = result.arguments.get("player_id")
    if raw is None and result.values:
        raw = result.values[0]
    if raw is None:
        return None
    player_id = parse_player_id(raw)
    if player_id is None:
        return None
    for player in players:
        if int(player.id) == player_id:
            return player
    return None


def autocomplete_players(
    players: list[Player],
    current: str,
    *,
    extra: tuple[tuple[str, str], ...] = (),
) -> list[tuple[str, str]]:
    query = current.lower().strip()
    options: list[tuple[str, str]] = list(extra)
    for player in players:
        label = player.display_name or player.mention
        value = str(player.id)
        if query and query not in label.lower() and query not in value:
            continue
        options.append((label, value))
    return options[:25]
