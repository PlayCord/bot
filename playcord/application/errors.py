"""Application-layer exceptions."""

from __future__ import annotations

from playcord.domain.errors import DomainError


class ApplicationError(Exception):
    """Base application-layer exception."""


class NotFoundError(ApplicationError):
    """Raised when a requested resource does not exist."""


class ForbiddenError(ApplicationError):
    """Raised when a user may not perform an operation."""


class WrappedDomainError(ApplicationError):
    """Wraps a domain failure at the application boundary."""

    def __init__(self, error: DomainError):
        super().__init__(str(error))
        self.error = error
