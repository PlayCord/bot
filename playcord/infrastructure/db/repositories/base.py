"""Shared typing for repository classes backed by :class:`~playcord.infrastructure.db.database.Database`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from playcord.infrastructure.db.database import Database


@runtime_checkable
class DatabaseBacked(Protocol):
    """Repositories hold a single ``database`` handle for SQL operations."""

    database: Database
