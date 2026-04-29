"""Replay frame reconstruction and lightweight frame caching."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from playcord.api import (
    GameContext,
    MessageLayout,
    ReplayableGame,
    ReplayState,
    RuntimeGame,
)
from playcord.core.player import Player
from playcord.games import GAME_BY_KEY

if TYPE_CHECKING:
    from playcord.infrastructure.database import (
        GameRepository,
        MatchRepository,
        PlayerRepository,
        ReplayRepository,
    )

PRECOMPUTE_FRAME_LIMIT = 200
_FRAME_CACHE_LIMIT = 512
_PRECOMPUTED_FRAME_CACHE_LIMIT = 128
_PRECOMPUTED_FRAMES: OrderedDict[int, list[MessageLayout]] = OrderedDict()
_FRAME_CACHE: OrderedDict[tuple[int, int], MessageLayout] = OrderedDict()


@dataclass(slots=True)
class ReplayDataSource:
    matches_repository: MatchRepository
    games_repository: GameRepository
    players_repository: PlayerRepository
    replays_repository: ReplayRepository


@dataclass(slots=True)
class ReplayContext:
    match_id: int
    game_label: str
    replay_display: str
    global_summary: str | None
    game_key: str | None
    plugin_class: type[RuntimeGame] | None
    players: list[Player]
    match_options: dict[str, Any]
    events: list[dict[str, Any]]


def supports_replay_api(plugin_class: type[RuntimeGame] | None) -> bool:
    if plugin_class is None:
        return False
    return issubclass(plugin_class, ReplayableGame)


def replay_move_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if str(event.get("type")) == "move"]


def replay_frame_count(events: list[dict[str, Any]]) -> int:
    return max(1, len(replay_move_events(events)) + 1)


def load_replay_context(
    match_id: int,
    *,
    source: ReplayDataSource,
) -> ReplayContext | None:
    match = source.matches_repository.get(match_id)
    if match is None:
        return None

    game = source.games_repository.get_by_id(match.game_id)
    game_key = game.game_name if game is not None else None
    game_label = (
        (game.display_name if game is not None else None)
        or (game.game_name if game is not None else None)
        or str(match.game_id)
    )
    replay_display = (match.match_code or "").strip() or str(match.match_id)
    plugin_class: type[RuntimeGame] | None = None
    if game_key:
        registry_game = GAME_BY_KEY.get(game_key)
        if registry_game is not None:
            plugin_class = registry_game.load()

    participants = source.matches_repository.get_participants(match.match_id)
    players: list[Player] = []
    for participant in participants:
        user_id = int(participant.user_id)
        user = source.players_repository.get(user_id)
        players.append(
            Player(
                id=user_id,
                display_name=(getattr(user, "username", None) if user else None),
                is_bot=bool(getattr(user, "is_bot", False)) if user else False,
            ),
        )

    game_config = match.game_config if isinstance(match.game_config, dict) else {}
    match_options = game_config.get("match_options")
    if not isinstance(match_options, dict):
        match_options = {}

    metadata = match.metadata if isinstance(match.metadata, dict) else {}
    global_summary = metadata.get("outcome_global_summary")
    if global_summary is not None:
        global_summary = str(global_summary).strip() or None

    events = source.replays_repository.get_events(match.match_id)
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
    plugin: RuntimeGame,
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
        ),
    )


def build_frames(
    plugin_class: type[RuntimeGame],
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
    _PRECOMPUTED_FRAMES.move_to_end(match_id)
    while len(_PRECOMPUTED_FRAMES) > _PRECOMPUTED_FRAME_CACHE_LIMIT:
        _PRECOMPUTED_FRAMES.popitem(last=False)


def get_precomputed_frames(match_id: int) -> list[MessageLayout] | None:
    frames = _PRECOMPUTED_FRAMES.get(match_id)
    if frames is None:
        return None
    _PRECOMPUTED_FRAMES.move_to_end(match_id)
    return list(frames)


def invalidate_match_cache(match_id: int) -> None:
    _PRECOMPUTED_FRAMES.pop(match_id, None)
    stale = [key for key in _FRAME_CACHE if key[0] == match_id]
    for key in stale:
        _FRAME_CACHE.pop(key, None)


def frame_for_index(
    *,
    match_id: int,
    frame_index: int,
    plugin_class: type[RuntimeGame],
    events: list[dict[str, Any]],
    players: list[Player],
    match_options: dict[str, Any],
    game_key: str,
) -> MessageLayout | None:
    frames = _PRECOMPUTED_FRAMES.get(match_id)
    if frames:
        _PRECOMPUTED_FRAMES.move_to_end(match_id)
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
