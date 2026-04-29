"""Match interruption helpers for unrecoverable runtime errors."""

from __future__ import annotations

from typing import Any

from playcord.application.runtime_context import get_container
from playcord.infrastructure.analytics_client import register_event
from playcord.infrastructure.database.models import EventType, MatchStatus
from playcord.infrastructure.db_thread import run_in_thread
from playcord.infrastructure.logging import get_logger

log = get_logger("application.match_interrupt")


def _reason_payload(error: BaseException, *, trace_id: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "error",
        "exception": type(error).__name__,
        "detail": str(error)[:500],
    }
    if trace_id:
        payload["trace_id"] = trace_id
    return payload


def _release_interface_locks(interface: Any) -> None:
    reg = get_container().registry
    for player in getattr(interface, "players", []) or []:
        reg.user_to_game.pop(player, None)
        player_id = getattr(player, "id", None)
        if player_id is not None:
            reg.user_to_game.pop(player_id, None)

    thread = getattr(interface, "thread", None)
    thread_id = getattr(thread, "id", None)
    if thread_id is not None:
        reg.discard_thread_cache(int(thread_id))
        reg.games_by_thread_id.pop(int(thread_id), None)


async def interrupt_match(
    interface: Any,
    error: BaseException,
    *,
    trace_id: str | None = None,
    logger=None,
) -> None:
    logger = logger or log
    if getattr(interface, "_interrupt_started", False):
        return

    interface._interrupt_started = True
    interface.ending_game = True

    reason_payload = _reason_payload(error, trace_id=trace_id)
    match_id = getattr(interface, "game_id", None)
    thread = getattr(interface, "thread", None)

    try:
        if match_id is not None:
            await run_in_thread(
                get_container().matches_repository.update_status,
                match_id,
                MatchStatus.INTERRUPTED.value,
                metadata_patch={"reason": reason_payload},
            )
    except Exception:
        logger.exception(
            "Failed to mark match interrupted match_id=%s trace_id=%s",
            match_id,
            trace_id,
        )

    _release_interface_locks(interface)

    try:
        register_event(
            EventType.ERROR_OCCURRED,
            user_id=getattr(getattr(interface, "creator", None), "id", None),
            guild_id=getattr(getattr(thread, "guild", None), "id", None),
            game_type=getattr(interface, "game_type", None),
            match_id=match_id,
            metadata={"reason": reason_payload},
        )
    except Exception:
        logger.exception("Failed to register game_errored analytics event")

    if thread is not None:
        try:
            await thread.edit(locked=True, archived=True, reason="game_error")
        except Exception:
            logger.exception(
                "Failed to archive errored thread match_id=%s trace_id=%s",
                match_id,
                trace_id,
            )
