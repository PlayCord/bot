"""Typed callback descriptor helpers for game metadata."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class HandlerRef:
    """Reference a handler by attribute name on a runtime game instance."""

    name: str


HandlerSpec = str | HandlerRef | Callable[..., Any] | None


def handler(name: str) -> HandlerRef:
    """Create a typed handler reference."""
    return HandlerRef(name=name)
