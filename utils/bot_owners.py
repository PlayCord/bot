"""Bot owner user IDs: :data:`configuration.constants.OWNERS` plus Developer Portal application owner(s)."""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from configuration.constants import LOGGING_ROOT, OWNERS

if TYPE_CHECKING:
    import discord

log = logging.getLogger(LOGGING_ROOT)

# Configured co-owners / operators (always treated as owners).
STATIC_OWNER_IDS: frozenset[int] = frozenset(int(x) for x in OWNERS)


def portal_owner_ids_from_appinfo(app_info: Any) -> frozenset[int]:
    """Extract owner user id(s) from :meth:`discord.Client.application_info` result."""
    ids: set[int] = set()
    owner = getattr(app_info, "owner", None)
    if owner is not None:
        oid = getattr(owner, "id", None)
        if oid is not None:
            ids.add(int(oid))
    team = getattr(app_info, "team", None)
    if team is not None:
        toid = getattr(team, "owner_id", None)
        if toid is not None:
            ids.add(int(toid))
    return frozenset(ids)


async def resolve_effective_owner_ids(client: discord.Client) -> frozenset[int]:
    """Merge ``STATIC_OWNER_IDS`` with portal owner(s). Falls back to static-only if the API call fails."""
    merged: set[int] = set(STATIC_OWNER_IDS)
    try:
        app_info = await client.application_info()
    except Exception:
        log.warning("application_info() failed; using STATIC_OWNER_IDS only for owner checks", exc_info=True)
        return frozenset(merged)
    merged.update(portal_owner_ids_from_appinfo(app_info))
    return frozenset(merged)
