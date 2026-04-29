"""Domain-level exception hierarchy."""

from __future__ import annotations


class DomainError(Exception):
    """Base exception for domain-level failures."""


class ValidationError(DomainError):
    """Raised when user-provided input is invalid."""


class RuleViolation(DomainError):
    """Raised when a move breaks a game's rules."""


class IllegalMove(RuleViolation):
    """Raised when a move cannot be applied to the current state."""


class NotPlayersTurn(RuleViolation):
    """Raised when a player acts out of turn."""


class ConfigurationError(DomainError):
    """Raised when game or match configuration is invalid."""
