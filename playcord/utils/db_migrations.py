"""
Apply versioned database migrations tracked in database_migrations.

Starting from 2.0.0 - clean rebase
with all historical migrations (1.0.0-1.2.5) consolidated.No backwards compatibility maintained.
"""

from __future__ import annotations

import hashlib

from playcord.utils.logging_config import get_logger

logger = get_logger("database.migrations")

MIGRATIONS: list[tuple[str, str, list[str]]] = [
    (
        "2.0.0",
        "Rebased baseline schema consolidating all migrations 1.0.0-1.2.5. Start fresh from clean state.",
        [],
    ),
]


def get_migration_hash(migration_sql: str) -> str:
    """Compute SHA256 hash of migration SQL for integrity checking."""
    return hashlib.sha256(migration_sql.strip().encode("utf-8")).hexdigest()


def apply_migrations(database):
    """Apply all pending migrations in order, tracking by version."""
    cur = database.cursor()

    try:
        # Create database_migrations table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS database_migrations (
                version TEXT PRIMARY KEY,
                description TEXT,
                applied_at TIMESTAMPTZ DEFAULT NOW(),
                sql_hash VARCHAR(64)
            );
            """)
        database.commit()
    except Exception as e:
        logger.error(f"Failed to create database_migrations table: {e}")
        database.rollback()
        raise

    applied_versions = set()
    try:
        cur.execute("SELECT version FROM database_migrations;")
        applied_versions = {row[0] for row in cur.fetchall()}
    except Exception as e:
        logger.warning(f"Could not fetch applied migrations: {e}")

    for version, description, statements in MIGRATIONS:
        if version in applied_versions:
            logger.info(f"Skipping already-applied migration {version}")
            continue

        logger.warning(f"Applying database migration {version} ({description})")

        try:
            for stmt in statements:
                stmt = stmt.strip()
                if not stmt:
                    continue
                logger.debug(f"Executing: {stmt[:100]}...")
                cur.execute(stmt)

            # Track the migration
            migration_text = "\n".join(statements)
            sql_hash = get_migration_hash(migration_text)

            cur.execute(
                """
                INSERT INTO database_migrations (version, description, sql_hash)
                VALUES (%s, %s, %s)
                ON CONFLICT (version) DO UPDATE SET
                    description = EXCLUDED.description,
                    sql_hash = EXCLUDED.sql_hash;
                """,
                (version, description, sql_hash),
            )
            database.commit()
            logger.info(f"✓ Migration {version} applied successfully")

        except Exception as e:
            logger.error(f"Transaction failed, rolled back: {e}")
            database.rollback()
            logger.error(f"Migration {version} failed ({type(e).__name__})")
            raise Exception(f"Migration {version} failed: {e}") from e
