"""Bot owner user IDs from app config plus Developer Portal application owner(s)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from playcord.infrastructure.logging import get_logger

if TYPE_CHECKING:
    import discord

log = get_logger("bot_owners")


def get_configured_static_owner_ids() -> frozenset[int]:
    """User IDs from ``bot.owner_user_ids`` in config and/or ``PLAYCORD_OWNER_IDS``."""
    try:
        from playcord.infrastructure.config import get_settings

        return frozenset(int(x) for x in get_settings().bot.owner_user_ids)
    except Exception:
        raw = os.getenv("PLAYCORD_OWNER_IDS", "")
        if not raw.strip():
            return frozenset()
        out: set[int] = set()
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                out.add(int(part))
            except ValueError:
                log.warning("Invalid integer in PLAYCORD_OWNER_IDS: %r", part)
        return frozenset(out)


def portal_owner_ids_from_appinfo(app_info: Any) -> frozenset[int]:
    """Extract owner user id(s) from :meth:`discord.Client.application_info` result."""
    ids: set[int] = set()
    log.debug("portal_owner_ids_from_appinfo: extracting from app_info=%r", app_info)

    owner = getattr(app_info, "owner", None)
    if owner is not None:
        oid = getattr(owner, "id", None)
        if oid is not None:
            try:
                oid_i = int(oid)
                ids.add(oid_i)
                log.debug(
                    "portal_owner_ids_from_appinfo: found application owner id=%d",
                    oid_i,
                )
            except (TypeError, ValueError):
                log.warning(
                    "portal_owner_ids_from_appinfo: invalid owner id value=%r",
                    oid,
                )

    team = getattr(app_info, "team", None)
    if team is not None:
        toid = getattr(team, "owner_id", None)
        if toid is not None:
            try:
                toid_i = int(toid)
                ids.add(toid_i)
                log.debug(
                    "portal_owner_ids_from_appinfo: found team owner id=%d",
                    toid_i,
                )
            except (TypeError, ValueError):
                log.warning(
                    "portal_owner_ids_from_appinfo: invalid team owner id value=%r",
                    toid,
                )

    log.debug("portal_owner_ids_from_appinfo: final extracted ids=%s", sorted(ids))
    return frozenset(ids)


async def resolve_effective_owner_ids(client: discord.Client) -> frozenset[int]:
    """Merge configured owner IDs with portal owner(s). Falls back
    to static-only if the API call fails.
    """
    merged: set[int] = set(get_configured_static_owner_ids())
    log.debug(
        "resolve_effective_owner_ids: starting with configured owner ids=%s",
        sorted(merged),
    )

    try:
        log.debug(
            "resolve_effective_owner_ids: requesting application_info() from client=%r",
            client,
        )
        app_info = await client.application_info()
        log.debug("resolve_effective_owner_ids: received application_info=%r", app_info)
    except Exception:
        log.warning(
            "resolve_effective_owner_ids: application_info() failed; using "
            "configured owner ids only for owner checks",
            exc_info=True,
        )
        return frozenset(merged)

    try:
        portal_ids = portal_owner_ids_from_appinfo(app_info)
        log.debug(
            "resolve_effective_owner_ids: portal owner ids=%s",
            sorted(portal_ids),
        )
    except Exception:
        log.exception(
            "resolve_effective_owner_ids: failed to extract "
            "portal owner ids from app_info=%r",
            app_info,
        )
        portal_ids = frozenset()

    merged.update(portal_ids)
    log.info("resolve_effective_owner_ids: effective owner ids=%s", sorted(merged))
    return frozenset(merged)
