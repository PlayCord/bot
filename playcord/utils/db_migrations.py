"""
Apply versioned database migrations tracked in database_migrations.

The schema is now clean-slate again, so fresh installs bootstrap from a single
baseline and historical migrations are intentionally dropped.
"""

from __future__ import annotations

import hashlib
import re

from playcord.utils.logging_config import get_logger

logger = get_logger("database.migrations")

MIGRATIONS: list[tuple[str, str, list[str]]] = [
    (
        "1.0.0",
        "Baseline schema is provided by schema.sql; no historical patch chain remains.",
        [],
    ),
    (
        "1.0.1",
        "Register game_errored analytics type (some paths / buffered events use this name).",
        [
            """
            INSERT INTO analytics_event_types (event_type, description)
            VALUES (
                'game_errored',
                'Game or match error (legacy name; prefer error_occurred in new code)'
            )
            ON CONFLICT (event_type) DO UPDATE SET
                description = EXCLUDED.description;
            """,
        ],
    ),
    (
        "1.0.2",
        "Drop redundant bot_messages.payload_digest column.",
        [
            """
            ALTER TABLE IF EXISTS bot_messages
            DROP COLUMN IF EXISTS payload_digest;
            """,
        ],
    ),
    (
        "1.0.3",
        "Remove legacy bot_messages table; runtime now tracks owned messages in memory.",
        [
            """
            DROP TABLE IF EXISTS bot_messages;
            """,
        ],
    ),
    (
        "1.0.4",
        "Set user_game_ratings defaults to conservative-rating baseline (mu=1500, sigma=166.6666666667).",
        [
            """
            ALTER TABLE IF EXISTS user_game_ratings
            ALTER COLUMN mu SET DEFAULT 1500.0;
            """,
            """
            ALTER TABLE IF EXISTS user_game_ratings
            ALTER COLUMN sigma SET DEFAULT 166.6666666667;
            """,
        ],
    ),
]


def apply_migrations(database) -> None:
    """Run any pending migrations (idempotent per version)."""
    for version, description, statements in MIGRATIONS:
        if not re.match(r"^\d+\.\d+(\.\d+)?$", version):
            logger.warning("Skipping migration with invalid version %r", version)
            continue
        row = database._execute_query(
            "SELECT 1 AS ok FROM database_migrations WHERE version = %s;",
            (version,),
            fetchone=True,
        )
        if row:
            continue
        logger.warning("Applying database migration %s", version)
        checksum = hashlib.sha256(
            "\n".join(stmt.strip() for stmt in statements).encode("utf-8")
        ).hexdigest()
        try:
            with database.transaction() as cur:
                for stmt in statements:
                    cur.execute(stmt.strip())
                cur.execute(
                    """
                    INSERT INTO database_migrations (version, description, checksum)
                    VALUES (%s, %s, %s);
                    """,
                    (version, description, checksum),
                )
        except Exception:
            logger.exception("Migration %s failed", version)
            raise
        logger.warning("Migration %s applied successfully", version)
