"""Database pool lifecycle."""

from __future__ import annotations

from dataclasses import dataclass

from playcord.infrastructure.config import DatabaseSettings
from playcord.infrastructure.database.implementation.database import Database
from playcord.infrastructure.logging import get_logger

log = get_logger("infrastructure.db.pool")


@dataclass(slots=True)
class PoolManager:
    """Owns the database connection pool for the application."""

    settings: DatabaseSettings
    database: Database | None = None

    def connect(self) -> Database:
        if self.database is not None:
            return self.database

        self.database = Database(
            host=self.settings.host,
            port=self.settings.port,
            user=self.settings.user,
            password=self.settings.password,
            database=self.settings.database,
            pool_size=self.settings.pool_size,
            max_overflow=self.settings.max_overflow,
            pool_timeout=self.settings.pool_timeout,
        )
        log.info(
            "Database pool initialized for %s:%s/%s",
            self.settings.host,
            self.settings.port,
            self.settings.database,
        )
        return self.database

    def close(self) -> None:
        if self.database is None:
            return
        self.database.disconnect()
        self.database = None
