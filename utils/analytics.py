"""
Analytics module for the bot
Tracks events like game starts, game completions, command usage, etc.
"""
import json
import logging
import time
from datetime import datetime
from enum import Enum
from typing import Any

from utils.database import database as db

logger = logging.getLogger("playcord.analytics")


class EventType(Enum):
    """Types of events that can be tracked"""
    GAME_STARTED = "game_started"
    GAME_COMPLETED = "game_completed"
    GAME_ABANDONED = "game_abandoned"
    MATCHMAKING_STARTED = "matchmaking_started"
    MATCHMAKING_COMPLETED = "matchmaking_completed"
    MATCHMAKING_CANCELLED = "matchmaking_cancelled"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    COMMAND_USED = "command_used"
    MOVE_MADE = "move_made"
    ERROR_OCCURRED = "error_occurred"
    BOT_STARTED = "bot_started"
    GUILD_JOINED = "guild_joined"
    GUILD_LEFT = "guild_left"


# Fallback buffer when DB write fails (retry on flush)
_event_buffer: list[dict] = []


def register_event(
    event_type: EventType | str,
    metadata: dict[str, Any] | None = None,
    user_id: int | None = None,
    guild_id: int | None = None,
    game_type: str | None = None,
    match_id: int | None = None,
) -> None:
    """
    Register an analytics event (written to the database immediately when connected).
    """
    et = event_type.value if isinstance(event_type, EventType) else str(event_type)
    meta = dict(metadata or {})

    if db:
        try:
            db.record_analytics_event(
                event_type=et,
                user_id=user_id,
                guild_id=guild_id,
                game_type=game_type,
                match_id=match_id,
                metadata=meta,
            )
            logger.debug("Recorded analytics event: %s", et)
            return
        except Exception as e:
            logger.warning("Analytics direct write failed, buffering: %s", e)

    global _event_buffer
    _event_buffer.append(
        {
            "event_type": et,
            "user_id": user_id,
            "guild_id": guild_id,
            "game_type": game_type,
            "match_id": match_id,
            "metadata": meta,
        }
    )
    if len(_event_buffer) >= 20:
        flush_events()


def flush_events() -> int:
    """
    Flush buffered events (after failed writes) to storage.

    :return: Number of events flushed
    """
    global _event_buffer

    if not _event_buffer:
        return 0

    count = len(_event_buffer)
    events_to_flush = _event_buffer.copy()

    if not db:
        logger.warning("Database not connected, dropping %s buffered analytics events.", count)
        _event_buffer = []
        return 0

    flushed = 0
    try:
        for event in events_to_flush:
            db.record_analytics_event(
                event_type=event["event_type"],
                user_id=event["user_id"],
                guild_id=event["guild_id"],
                game_type=event["game_type"],
                match_id=event.get("match_id"),
                metadata=event.get("metadata") or {},
            )
            flushed += 1
        _event_buffer = []
        if flushed:
            logger.info("Flushed %s buffered analytics events.", flushed)
    except Exception as e:
        logger.error("Failed to flush analytics events: %s", e)
        if len(_event_buffer) > 500:
            _event_buffer = _event_buffer[-250:]

    return flushed


def get_event_stats() -> dict[str, int]:
    """
    Get statistics on buffered events.

    :return: Dictionary of event type counts
    """
    stats: dict[str, int] = {}
    for event in _event_buffer:
        t = event["event_type"]
        stats[t] = stats.get(t, 0) + 1
    return stats


class Timer:
    """Timer utility for measuring execution time."""

    def __init__(self):
        self._start_time = None

    @property
    def current_time(self):
        """Get the current elapsed time in milliseconds."""
        if self._start_time is not None:
            return round((time.perf_counter() - self._start_time) * 1000, 4)
        return 0

    def start(self):
        """Start a new timer"""

        self._start_time = time.perf_counter()
        return self

    def stop(self, use_ms=True, round_digits=4):
        """Stop the timer, and report the elapsed time"""
        if self._start_time is None:
            return None

        elapsed_time = time.perf_counter() - self._start_time
        self._start_time = None
        if use_ms:
            return round(elapsed_time * 1000, round_digits)
        else:
            return round(elapsed_time, round_digits)


def format_recent_event_row(row: dict[str, Any]) -> str:
    """One line for owner-facing analytics dump (Discord-safe length)."""
    meta = row.get("metadata")
    if meta is not None and not isinstance(meta, dict):
        try:
            meta = dict(meta)
        except Exception:
            meta = {"_raw": str(meta)[:80]}
    meta_s = ""
    if meta:
        try:
            meta_s = json.dumps(meta, separators=(",", ":"), ensure_ascii=False)
        except TypeError:
            meta_s = str(meta)
        if len(meta_s) > 120:
            meta_s = meta_s[:117] + "..."
    ts = row.get("timestamp")
    ts_s = ts.isoformat()[:19] if hasattr(ts, "isoformat") else str(ts)[:19]
    return (
        f"`{row.get('event_id')}` **{row.get('event_type')}** {ts_s} "
        f"u={row.get('user_id')} g={row.get('guild_id')} "
        f"match={row.get('match_id')} {meta_s}"
    )
