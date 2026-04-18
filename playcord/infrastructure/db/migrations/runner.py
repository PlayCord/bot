"""Migration runner for the refactored application container."""

from __future__ import annotations

from dataclasses import dataclass

from playcord.infrastructure.logging import get_logger

from playcord.utils import db_migrations
from playcord.utils.database import Database

log = get_logger("infrastructure.db.migrations")


@dataclass(slots=True)
class MigrationRunner:
    """Applies database migrations and startup maintenance steps."""

    analytics_retention_days: int = 30

    def apply(self, database: Database) -> None:
        db_migrations.apply_migrations(database)
        database.refresh_sql_assets()
        database.sync_games_from_code()
        database.cleanup_old_analytics(days=self.analytics_retention_days)
        interrupted = database.interrupt_stale_matches()
        if interrupted:
            log.warning(
                "Marked %s stale in-progress matches as interrupted during startup",
                interrupted,
            )
