"""Game metadata registry and installation from code."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from playcord.api.plugin import resolve_player_count
from playcord.infrastructure.constants import GAME_TYPES
from playcord.infrastructure.database.implementation.core.exceptions import (
    DatabaseError,
)
from playcord.infrastructure.database.models import Game, row_to_game

if TYPE_CHECKING:
    from playcord.infrastructure.database.implementation.database import Database


@dataclass(slots=True)
class GameRepository:
    """Registered game types, caching, and upsert from plugin metadata."""

    database: Database

    def _cache_game(self, game: Game | None) -> Game | None:
        if game is None:
            return None
        self._game_cache_by_id[game.game_id] = game
        self._game_cache_by_name[game.game_name] = game
        return game

    _game_cache_by_id: dict[int, Game] = field(default_factory=dict, init=False)
    _game_cache_by_name: dict[str, Game] = field(default_factory=dict, init=False)

    def clear_caches(self) -> None:
        self._game_cache_by_id.clear()
        self._game_cache_by_name.clear()

    def register_game(
        self,
        game_name: str,
        display_name: str,
        min_players: int,
        max_players: int,
        game_metadata: dict[str, Any] | None = None,
        game_schema_version: int = 1,
    ) -> int:
        metadata_json = json.dumps(game_metadata or {})
        query = """
            INSERT INTO games (game_name, display_name, min_players, max_players,
                              game_metadata, game_schema_version)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (game_name) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                min_players = EXCLUDED.min_players,
                max_players = EXCLUDED.max_players,
                game_metadata = EXCLUDED.game_metadata,
                game_schema_version = EXCLUDED.game_schema_version,
                updated_at = NOW()
            RETURNING game_id;
        """
        result = self.database.execute_query(
            query,
            (
                game_name,
                display_name,
                min_players,
                max_players,
                metadata_json,
                game_schema_version,
            ),
            fetchone=True,
        )
        game_id = result["game_id"] if result else None
        if game_id is not None:
            self._cache_game(
                Game(
                    game_id=game_id,
                    game_name=game_name,
                    display_name=display_name,
                    min_players=min_players,
                    max_players=max_players,
                    game_metadata=json.loads(metadata_json),
                    game_schema_version=game_schema_version,
                    is_active=True,
                ),
            )
        return game_id  # type: ignore[return-value]

    def sync_games_from_code(self) -> None:
        for game_name, (mod_name, cls_name) in GAME_TYPES.items():
            mod = importlib.import_module(mod_name)
            cls = getattr(mod, cls_name)
            metadata = cls.metadata
            display_name = getattr(
                metadata,
                "name",
                game_name.replace("_", " ").title(),
            )
            spec = resolve_player_count(cls)
            if isinstance(spec, list):
                min_p, max_p = min(spec), max(spec)
            elif spec is None:
                min_p, max_p = 2, 2
            else:
                min_p = max_p = int(spec)
            schema_ver = int(getattr(cls, "game_schema_version", 1))
            meta = {
                "summary": getattr(metadata, "summary", ""),
                "description": getattr(metadata, "description", ""),
            }
            self.register_game(
                game_name=game_name,
                display_name=display_name,
                min_players=min_p,
                max_players=max_p,
                game_metadata=meta,
                game_schema_version=schema_ver,
            )

    def get(self, game_name: str) -> Game | None:
        """Get game by name (alias: get_game in legacy)."""
        cached = self._game_cache_by_name.get(game_name)
        if cached is not None:
            return cached
        query = "SELECT * FROM games WHERE game_name = %s;"
        result = self.database.execute_query(query, (game_name,), fetchone=True)
        return self._cache_game(row_to_game(result) if result else None)

    def get_by_id(self, game_id: int) -> Game | None:
        """Get game by id."""
        cached = self._game_cache_by_id.get(game_id)
        if cached is not None:
            return cached
        query = "SELECT * FROM games WHERE game_id = %s;"
        result = self.database.execute_query(query, (game_id,), fetchone=True)
        return self._cache_game(row_to_game(result) if result else None)

    def reset_game_data(self, game_id: int) -> Game:
        game = self.get_by_id(game_id)
        if game is None:
            msg = f"Game {game_id} not found"
            raise ValueError(msg)

        game_name = game.game_name
        self.database.execute_query("DELETE FROM games WHERE game_id = %s;", (game_id,))
        self._game_cache_by_id.pop(game_id, None)
        self._game_cache_by_name.pop(game_name, None)

        self.sync_games_from_code()
        recreated = self.get(game_name)
        if recreated is None:
            msg = f"Game {game_name!r} was deleted but not recreated from code"
            raise DatabaseError(
                msg,
            )
        return recreated

    def get_game(self, game_name: str) -> Game | None:
        return self.get(game_name)
