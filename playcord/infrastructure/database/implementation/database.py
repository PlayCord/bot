"""PlayCord PostgreSQL connection pool and low-level query execution.

Domain operations live in :mod:`playcord.infrastructure.database.implementation.repositories`.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path
from typing import Any

try:
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
except ImportError as err:
    msg = "psycopg3 is required. Install with: pip install 'psycopg[binary,pool]'"
    raise ImportError(
        msg,
    ) from err

from playcord.infrastructure.database.implementation.core.exceptions import (
    DatabaseConnectionError,
)
from playcord.infrastructure.logging import get_logger

logger = get_logger("database")


class Database:
    """PostgreSQL connection pool for PlayCord.
    Repositories use :meth:`execute_query` and :meth:`transaction` for SQL.
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_timeout: int = 30,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_timeout = pool_timeout

        self.conninfo = (
            f"host={host} port={port} dbname={database} user={user} password={password}"
        )

        self.pool: ConnectionPool | None = None
        self.connect()

    def connect(self) -> None:
        """Initialize connection pool."""
        try:
            self.pool = ConnectionPool(
                conninfo=self.conninfo,
                min_size=2,
                max_size=self.pool_size,
                timeout=self.pool_timeout,
                kwargs={"row_factory": dict_row},
            )
            logger.info("Connected to PostgreSQL database: %s", self.database)
        except Exception as e:
            logger.exception("Error connecting to PostgreSQL: %s", e)
            self.pool = None
            msg = f"Could not connect to database: {e}"
            raise DatabaseConnectionError(msg) from e

    def disconnect(self) -> None:
        """Close connection pool."""
        if self.pool:
            self.pool.close()
            logger.info("Database connection pool closed.")

    def get_connection(self):
        """Get a connection from the pool."""
        if not self.pool:
            msg = "Connection pool not initialized"
            raise DatabaseConnectionError(msg)
        return self.pool.connection()

    def _load_sql_asset(self, relative_path: str) -> None:
        """Execute an idempotent SQL asset file (functions/views) shipped with PlayCord."""
        sql_dir = Path(__file__).resolve().parent / "sql"
        sql_path = sql_dir / Path(relative_path).name
        with sql_path.open("r", encoding="utf-8") as fh:
            sql_text = fh.read()
        with self.transaction() as cur:
            cur.execute(sql_text)

    def refresh_sql_assets(self) -> None:
        """Refresh SQL functions and views from the tracked asset files."""
        self._load_sql_asset("functions.sql")
        self._load_sql_asset("views.sql")

    @contextmanager
    def transaction(self):
        """Transaction context manager.

        Usage:
            with db.transaction() as cur:
                cur.execute("INSERT ...")
        """
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cur:
                    yield cur
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.exception("Transaction failed, rolled back: %s", e)
                raise

    def execute_query(
        self,
        query: str,
        params: tuple | None = None,
        fetchone: bool = False,
        fetchall: bool = False,
    ):
        """Execute a query with automatic connection management.

        Args:
            query: SQL query string
            params: Query parameters tuple
            fetchone: Return single row
            fetchall: Return all rows

        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(query, params or ())

                    if fetchone:
                        return cur.fetchone()
                    if fetchall:
                        return cur.fetchall()
                    conn.commit()
                    return None

                except Exception as e:
                    conn.rollback()
                    logger.warning(
                        "Error executing query %s... (params=%s, fetchone=%s, fetchall=%s): %s",
                        query[:100],
                        params,
                        fetchone,
                        fetchall,
                        e,
                    )
                    raise

    async def aexecute_query(
        self,
        query: str,
        params: tuple | None = None,
        fetchone: bool = False,
        fetchall: bool = False,
    ) -> Any:
        """Async wrapper: run :meth:`execute_query` in a worker thread.

        Use from coroutines so psycopg does not block the Discord event loop.
        """
        return await asyncio.to_thread(
            self.execute_query,
            query,
            params,
            fetchone,
            fetchall,
        )
