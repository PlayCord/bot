"""Schema-wide maintenance, reporting, and health."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from playcord.infrastructure.database.implementation.core import migrations

if TYPE_CHECKING:
    from playcord.infrastructure.database.implementation.database import Database


@dataclass(slots=True)
class MaintenanceRepository:
    database: Database
    games: Any  # GameRepository

    def reset_all_data(self) -> None:
        self.games.clear_caches()
        with self.database.get_connection() as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("DROP SCHEMA IF EXISTS public CASCADE;")
                cur.execute("CREATE SCHEMA public;")
                cur.execute("DROP TABLE IF EXISTS database_migrations;")
            conn.autocommit = False

        migrations.apply_migrations(self.database)
        self.database.refresh_sql_assets()
        self.games.sync_games_from_code()
