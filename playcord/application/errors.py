"""Application-layer exceptions."""


class ApplicationError(Exception):
    """Base application-layer exception."""


class NotFoundError(ApplicationError):
    """Raised when a requested resource does not exist."""


class ForbiddenError(ApplicationError):
    """Raised when a user may not perform an operation."""
