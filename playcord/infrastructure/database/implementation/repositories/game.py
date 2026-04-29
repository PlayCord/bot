"""Game metadata registry, installation from code, and leaderboard delegation."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from playcord.api.plugin import resolve_player_count
from playcord.api.trueskill_config import get_trueskill_parameters
from playcord.core.rating import DEFAULT_MU, STARTING_RATING
from playcord.infrastructure.config import get_settings
from playcord.infrastructure.constants import GAME_TYPES
from playcord.infrastructure.database.implementation.core.exceptions import (
    DatabaseError,
)
from playcord.infrastructure.database.implementation.repositories.leaderboard import (
    LeaderboardRepository,
)
from playcord.infrastructure.database.models import Game, row_to_game

if TYPE_CHECKING:
    from playcord.infrastructure.database.implementation.database import Database


@dataclass(slots=True)
class GameRepository:
    """Registered game types, caching, and upsert from plugin metadata."""

    database: Database
    _leaderboard: LeaderboardRepository = field(init=False)

    def __post_init__(self) -> None:
        self._leaderboard = LeaderboardRepository(self.database)

    @property
    def leaderboard(self) -> LeaderboardRepository:
        return self._leaderboard

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

    def get_leaderboard(
        self,
        member_user_ids: list[int],
        game_id: int,
        *,
        limit: int = 10,
        offset: int = 0,
        min_matches: int = 5,
    ) -> list[dict[str, Any]]:
        return self._leaderboard.get_leaderboard(
            member_user_ids,
            game_id,
            limit,
            offset,
            min_matches,
        )

    def get_global_leaderboard(
        self,
        game_id: int,
        *,
        limit: int = 10,
        offset: int = 0,
        min_matches: int = 5,
    ) -> list[dict[str, Any]]:
        return self._leaderboard.get_global_leaderboard(
            game_id,
            limit=limit,
            offset=offset,
            min_matches=min_matches,
        )

    def register_game(
        self,
        game_name: str,
        display_name: str,
        min_players: int,
        max_players: int,
        rating_config: dict[str, float],
        game_metadata: dict[str, Any] | None = None,
        game_schema_version: int = 1,
    ) -> int:
        config_json = json.dumps(rating_config)
        metadata_json = json.dumps(game_metadata or {})
        query = """
            INSERT INTO games (game_name, display_name, min_players, max_players,
                              rating_config, game_metadata, game_schema_version)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            ON CONFLICT (game_name) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                min_players = EXCLUDED.min_players,
                max_players = EXCLUDED.max_players,
                rating_config = EXCLUDED.rating_config,
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
                config_json,
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
                    rating_config=json.loads(config_json),
                    game_metadata=json.loads(metadata_json),
                    game_schema_version=game_schema_version,
                    is_active=True,
                ),
            )
        return game_id  # type: ignore[return-value]

    def sync_games_from_code(self) -> None:
        cfg = get_settings().ratings
        default_min_mu = float(cfg.min_mu)
        default_min_sigma = float(cfg.min_sigma)

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
            ts = get_trueskill_parameters(game_name)
            def_sigma = float(ts["sigma"] * STARTING_RATING)
            rating_config = {
                "sigma": float(ts["sigma"] * STARTING_RATING),
                "beta": float(ts["beta"] * STARTING_RATING),
                "tau": float(ts["tau"] * STARTING_RATING),
                "draw": float(ts["draw"]),
                "default_mu": float(DEFAULT_MU),
                "default_sigma": def_sigma,
                "min_mu": default_min_mu,
                "min_sigma": max(default_min_sigma, 0.001),
            }
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
                rating_config=rating_config,
                game_metadata=meta,
                game_schema_version=schema_ver,
            )

    def sync_matches_played_counts(self) -> int:
        result = self.database.execute_query(
            "SELECT sync_games_played_counts() AS n;",
            fetchone=True,
        )
        return int(result["n"]) if result else 0

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

    def list(self, *, active_only: bool = True) -> list[Game]:
        if active_only:
            query = "SELECT * FROM games WHERE is_active = TRUE ORDER BY game_name;"
        else:
            query = "SELECT * FROM games ORDER BY game_name;"
        results = self.database.execute_query(query, fetchall=True)
        games = [row_to_game(row) for row in results] if results else []
        for game in games:
            self._cache_game(game)
        return games

    def update_game_config(self, game_id: int, config: dict[str, Any]) -> None:
        config_json = json.dumps(config)
        query = """
            UPDATE games SET rating_config = %s::jsonb, updated_at = NOW()
            WHERE game_id = %s;
        """
        self.database.execute_query(query, (config_json, game_id))

    def deactivate_game(self, game_id: int) -> None:
        query = (
            "UPDATE games SET is_active = FALSE, updated_at = NOW() WHERE game_id = %s;"
        )
        self.database.execute_query(query, (game_id,))

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

    # --- Legacy / compatibility method names (delegate to the above) ---

    def get_game(self, game_name: str) -> Game | None:
        return self.get(game_name)

    def get_game_by_id(self, game_id: int) -> Game | None:
        return self.get_by_id(game_id)

    def get_all_games(self, active_only: bool = True) -> list[Game]:
        return self.list(active_only=active_only)

    def get_game_leaderboard(
        self,
        member_user_ids: list[int],
        game_name: str,
        limit: int = 10,
        min_matches: int = 5,
    ) -> list[dict[str, Any]]:
        game = self.get_game(game_name)
        if not game:
            return []
        return self.get_leaderboard(
            member_user_ids,
            game.game_id,
            limit=limit,
            min_matches=min_matches,
        )
