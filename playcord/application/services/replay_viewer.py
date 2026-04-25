"""Replay frame reconstruction and lightweight frame caching."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from playcord.domain.player import Player
from playcord.games import PLUGIN_BY_KEY
from playcord.games.api import GameContext, GamePlugin, MessageLayout, ReplayState
from playcord.utils import database as db

PRECOMPUTE_FRAME_LIMIT = 200
_FRAME_CACHE_LIMIT = 512
_PRECOMPUTED_FRAMES: dict[int, list[MessageLayout]] = {}
_FRAME_CACHE: OrderedDict[tuple[int, int], MessageLayout] = OrderedDict()


@dataclass(slots=True)
class ReplayContext:
    match_id: int
    game_label: str
    replay_display: str
    global_summary: str | None
    game_key: str | None
    plugin_class: type[GamePlugin] | None
    players: list[Player]
    match_options: dict[str, Any]
    events: list[dict[str, Any]]


def supports_replay_api(plugin_class: type[GamePlugin] | None) -> bool:
    if plugin_class is None:
        return False
    return (
        plugin_class.apply_replay_event is not GamePlugin.apply_replay_event
        and plugin_class.render_replay is not GamePlugin.render_replay
    )


def replay_move_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if str(event.get("type")) == "move"]


def replay_frame_count(events: list[dict[str, Any]]) -> int:
    return max(1, len(replay_move_events(events)) + 1)


def load_replay_context(match_id: int) -> ReplayContext | None:
    database = db.database
    if database is None:
        return None
    match = database.get_match(match_id)
    if match is None:
        return None
    game = database.get_game_by_id(match.game_id)
    game_key = game.game_name if game is not None else None
    game_label = (
        (game.display_name if game is not None else None)
        or (game.game_name if game is not None else None)
        or str(match.game_id)
    )
    replay_display = (match.match_code or "").strip() or str(match.match_id)
    plugin_class: type[GamePlugin] | None = None
    if game_key:
        plugin = PLUGIN_BY_KEY.get(game_key)
        if plugin is not None:
            plugin_class = plugin.load()

    participants = database.get_participants(match.match_id)
    players: list[Player] = []
    for participant in participants:
        user_id = int(participant.user_id)
        user = database.get_user(user_id)
        players.append(
            Player(
                id=user_id,
                display_name=(getattr(user, "username", None) if user else None),
                is_bot=bool(getattr(user, "is_bot", False)) if user else False,
            )
        )

    game_config = match.game_config if isinstance(match.game_config, dict) else {}
    match_options = game_config.get("match_options")
    if not isinstance(match_options, dict):
        match_options = {}

    metadata = match.metadata if isinstance(match.metadata, dict) else {}
    global_summary = metadata.get("outcome_global_summary")
    if global_summary is not None:
        global_summary = str(global_summary).strip() or None

    events = database.get_replay_events(match.match_id)
    return ReplayContext(
        match_id=match.match_id,
        game_label=game_label,
        replay_display=replay_display,
        global_summary=global_summary,
        game_key=game_key,
        plugin_class=plugin_class,
        players=players,
        match_options=dict(match_options),
        events=events,
    )


def _initial_state_from_events(
    events: list[dict[str, Any]],
    *,
    game_key: str,
    players: list[Player],
    match_options: dict[str, Any],
) -> ReplayState | None:
    for event in events:
        if str(event.get("type")) != "replay_init":
            continue
        raw_state = event.get("state")
        if not isinstance(raw_state, dict):
            continue
        raw_options = raw_state.get("match_options")
        resolved_options = (
            dict(raw_options) if isinstance(raw_options, dict) else dict(match_options)
        )
        try:
            move_index = int(raw_state.get("move_index", 0) or 0)
        except (TypeError, ValueError):
            move_index = 0
        return ReplayState(
            game_key=str(raw_state.get("game_key", game_key)),
            players=list(players),
            match_options=resolved_options,
            move_index=move_index,
            state=raw_state.get("state"),
        )
    return None


def _initial_state(
    plugin: GamePlugin,
    *,
    game_key: str,
    players: list[Player],
    match_options: dict[str, Any],
    events: list[dict[str, Any]],
) -> ReplayState | None:
    restored = _initial_state_from_events(
        events,
        game_key=game_key,
        players=players,
        match_options=match_options,
    )
    if restored is not None:
        return restored
    return plugin.initial_replay_state(
        GameContext(
            match_id=0,
            game_key=game_key,
            players=list(players),
            match_options=dict(match_options),
        )
    )


def build_frames(
    plugin_class: type[GamePlugin],
    events: list[dict[str, Any]],
    players: list[Player],
    match_options: dict[str, Any],
    *,
    game_key: str,
) -> list[MessageLayout]:
    if not supports_replay_api(plugin_class):
        return []
    plugin = plugin_class(players=list(players), match_options=dict(match_options))
    state = _initial_state(
        plugin,
        game_key=game_key,
        players=players,
        match_options=match_options,
        events=events,
    )
    if state is None:
        return []

    first = plugin.render_replay(state)
    if first is None:
        return []
    frames = [first]
    for event in replay_move_events(events):
        next_state = plugin.apply_replay_event(state, event)
        if next_state is None:
            continue
        state = next_state
        frame = plugin.render_replay(state)
        if frame is None:
            continue
        frames.append(frame)
    return frames


def cache_precomputed_frames(match_id: int, frames: list[MessageLayout]) -> None:
    _PRECOMPUTED_FRAMES[match_id] = list(frames)


def get_precomputed_frames(match_id: int) -> list[MessageLayout] | None:
    frames = _PRECOMPUTED_FRAMES.get(match_id)
    return list(frames) if frames is not None else None


def frame_for_index(
    *,
    match_id: int,
    frame_index: int,
    plugin_class: type[GamePlugin],
    events: list[dict[str, Any]],
    players: list[Player],
    match_options: dict[str, Any],
    game_key: str,
) -> MessageLayout | None:
    frames = _PRECOMPUTED_FRAMES.get(match_id)
    if frames:
        idx = max(0, min(frame_index, len(frames) - 1))
        return frames[idx]

    move_events = replay_move_events(events)
    idx = max(0, min(frame_index, len(move_events)))
    cache_key = (match_id, idx)
    cached = _FRAME_CACHE.get(cache_key)
    if cached is not None:
        _FRAME_CACHE.move_to_end(cache_key)
        return cached

    plugin = plugin_class(players=list(players), match_options=dict(match_options))
    state = _initial_state(
        plugin,
        game_key=game_key,
        players=players,
        match_options=match_options,
        events=events,
    )
    if state is None:
        return None
    for event in move_events[:idx]:
        next_state = plugin.apply_replay_event(state, event)
        if next_state is None:
            continue
        state = next_state

    frame = plugin.render_replay(state)
    if frame is None:
        return None
    _FRAME_CACHE[cache_key] = frame
    _FRAME_CACHE.move_to_end(cache_key)
    while len(_FRAME_CACHE) > _FRAME_CACHE_LIMIT:
        _FRAME_CACHE.popitem(last=False)
    return frame
