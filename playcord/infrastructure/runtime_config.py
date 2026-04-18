"""Binds loaded :class:`Settings` for code paths that cannot receive DI (e.g. legacy DB layer)."""

from __future__ import annotations

from playcord.domain.errors import ConfigurationError
from playcord.infrastructure.config import Settings

_bound: Settings | None = None


def bind_settings(settings: Settings) -> None:
    """Call once during application bootstrap (before DB code reads floors or retention)."""
    global _bound
    _bound = settings


def get_settings() -> Settings:
    if _bound is None:
        raise ConfigurationError(
            "Application settings are not bound; call bind_settings() from bootstrap"
        )
    return _bound


def reset_settings_binding() -> None:
    """Test helper."""
    global _bound
    _bound = None
