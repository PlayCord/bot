"""Database-specific exception types."""


class DatabaseConnectionError(Exception):
    """Raised when the database connection cannot be established."""


class DatabaseError(Exception):
    """Raised for generic database operation failures."""
