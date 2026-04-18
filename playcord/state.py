"""Process-wide session maps (single source of truth for in-memory game state)."""

from __future__ import annotations

from typing import Any

# Active game thread id → GameInterface
CURRENT_GAMES: dict[int, Any] = {}

# Lobby message id → matchmaking interface
CURRENT_MATCHMAKING: dict[int, Any] = {}

# User id → active game interface
IN_GAME: dict[int, Any] = {}

# User id → matchmaking interface
IN_MATCHMAKING: dict[int, Any] = {}

# Autocomplete caches keyed by channel / user / handler path
AUTOCOMPLETE_CACHE: dict[int, Any] = {}
