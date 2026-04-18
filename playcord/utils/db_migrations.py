"""
Apply versioned database migrations tracked in database_migrations.

The schema is now clean-slate again, so fresh installs bootstrap from a single
baseline and historical migrations are intentionally dropped.
"""

from __future__ import annotations

import hashlib
import re
from typing import List, Tuple

from playcord.utils.logging_config import get_logger

logger = get_logger("database.migrations")

MIGRATIONS: List[Tuple[str, str, List[str]]] = [
    (
        "1.0.0",
        "Baseline schema is provided by schema.sql; no historical patch chain remains.",
        [],
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
