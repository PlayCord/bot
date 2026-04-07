"""
PlayCord PostgreSQL Database Interface
Comprehensive database operations with transaction support and connection pooling.
"""

import json
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import discord
try:
    import psycopg  # psycopg3
    from psycopg import errors as pg_errors
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
except ImportError:
    # Fallback error message
    raise ImportError(
        "psycopg3 is required. Install with: pip install 'psycopg[binary,pool]'"
    )

from api.Player import Player
from configuration import constants
from configuration.constants import GAME_TYPES, MU
from utils.trueskill_params import get_trueskill_parameters
from utils.match_codes import generate_match_code
from utils import db_migrations
from utils.models import (
    User, Guild, Game, Rating, Match, Participant, Move,
    MatchStatus, EventType,
    row_to_user, row_to_guild, row_to_game, row_to_rating,
    row_to_match, row_to_participant, row_to_move
)

logger = logging.getLogger("playcord.database")


# ============================================================================
# EXCEPTIONS
# ============================================================================

class DatabaseConnectionError(Exception):
    """Exception raised when failed to connect to the database."""
    pass


class DatabaseError(Exception):
    """Generic database operation error."""
    pass


# ============================================================================
# INTERNAL PLAYER CLASSES (for compatibility)
# ============================================================================

class InternalPlayerRatingStatistic:
    """Rating statistic for a specific game"""
    def __init__(self, name: str, mu: Optional[float], sigma: Optional[float]):
        self.name = name
        if mu is None:
            self.mu = MU
            if name in GAME_TYPES:
                self.sigma = get_trueskill_parameters(name)["sigma"] * MU
            else:
                self.sigma = MU / 3.0  # Default sigma
            self.stored = False
        else:
            self.mu = mu
            self.sigma = sigma
            self.stored = True


class InternalPlayer:
    """Internal player representation with ratings"""
    def __init__(
        self,
        ratings: Dict[str, Dict[str, float]],
        user: Optional[discord.User | discord.Object] = None,
        metadata: Optional[Dict] = None,
        id: Optional[int] = None
    ):
        # User info
        if isinstance(user, discord.User):
            self.name = user.name
        else:
            self.name = None

        if user is not None:
            self.id = user.id
        else:
            self.id = id

        if metadata is not None:
            self.metadata = metadata
        else:
            self.metadata = {}

        # No servers in new schema
        self.servers = []

        # Blind assignments
        self.user = user
        self.ratings = ratings
        self.player_data = {}
        self.moves_made = 0

        self._update_ratings(self.ratings)

    def _update_ratings(self, ratings: Dict[str, Dict[str, float]]):
        """Update rating attributes from ratings dict"""
        rating_keys = set(GAME_TYPES) | set(ratings)
        for key in rating_keys:
            if key not in ratings:
                ratings[key] = {
                    "mu": MU,
                    "sigma": get_trueskill_parameters(key)["sigma"] * MU,
                }
            setattr(
                self,
                key,
                InternalPlayerRatingStatistic(
                    key,
                    ratings[key]["mu"],
                    ratings[key]["sigma"]
                )
            )

    @property
    def mention(self) -> str:
        """Discord mention string"""
        return f"<@{self.id}>"

    @property
    def display_name(self) -> str:
        """Human-readable player name for table rendering."""
        return self.name or f"@{self.id}"

    def get_formatted_elo(
        self,
        game_type: str,
        include_global_rank: bool = False,
        game_id: int = None,
        global_rank: int | None = None,
    ) -> str:
        """
        Get formatted rating string with uncertainty indicator.
        
        :param game_type: The game type key (e.g., 'tictactoe')
        :param include_global_rank: If True, include global rank suffix for top players
        :param game_id: Required if include_global_rank is True
        :return: Formatted rating string like "1000", "1000?", or "1000 (Top 5 globally)"
        """
        rating = getattr(self, game_type, None)
        if rating is None or rating.mu is None:
            return "No Rating"
        
        # Use 20% uncertainty threshold (sigma vs mu)
        if rating.sigma > 0.20 * rating.mu:
            base_rating = str(round(rating.mu)) + "?"
        else:
            base_rating = str(round(rating.mu))
        
        # Rank decoration is supplied by the caller to avoid hidden DB I/O in the model.
        if include_global_rank and game_id is not None and global_rank is not None:
            if global_rank <= 100:  # Top 100 players
                if global_rank == 1:
                    base_rating += " 🏆 #1 Globally"
                elif global_rank <= 3:
                    base_rating += f" 🥇 Top {global_rank} Globally"
                elif global_rank <= 10:
                    base_rating += f" ⭐ Top {global_rank} Globally"
                elif global_rank <= 100:
                    base_rating += f" (Top {global_rank} Globally)"
        
        return base_rating

    def __eq__(self, other):
        if not isinstance(other, InternalPlayer):
            return False
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __str__(self):
        return self.mention

    def __repr__(self):
        if self.user is not None:
            return f"InternalPlayer(id={self.id}, bot={self.user.bot}, ratings={self.ratings})"
        else:
            return f"InternalPlayer(id={self.id}, bot=no-user-provided, ratings={self.ratings})"


def get_shallow_player(user: discord.User) -> InternalPlayer:
    """Create a shallow player with no ratings"""
    return InternalPlayer(ratings={}, user=user)


def internal_player_to_player(internal_player: InternalPlayer, game_type: str) -> Player:
    """Convert InternalPlayer to API Player object"""
    rating = getattr(internal_player, game_type)
    user = internal_player.user
    if user is not None:
        uid = user.id
        uname = user.name if isinstance(user, discord.User) else (internal_player.name or f"User {uid}")
    else:
        uid = internal_player.id
        uname = internal_player.name or (f"User {uid}" if uid is not None else "Unknown")
    return Player(
        mu=rating.mu,
        sigma=rating.sigma,
        ranking=None,
        id=uid,
        name=uname,
    )


# ============================================================================
# DATABASE CLASS
# ============================================================================

class Database:
    """
    PostgreSQL database interface for PlayCord.
    Supports transactions, connection pooling, and comprehensive CRUD operations.
    """

    def __init__(self, host: str, port: int, user: str, password: str, database: str,
                 pool_size: int = 10, max_overflow: int = 20, pool_timeout: int = 30):
        """
        Initialize database connection pool.

        Args:
            host: Database host
            port: Database port
            user: Database user
            password: Database password
            database: Database name
            pool_size: Number of connections in pool
            max_overflow: Max connections beyond pool_size
            pool_timeout: Seconds to wait for connection from pool
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_timeout = pool_timeout

        # Connection string
        self.conninfo = (
            f"host={host} port={port} dbname={database} "
            f"user={user} password={password}"
        )

        # Connection pool
        self.pool: Optional[ConnectionPool] = None
        self._game_cache_by_id: Dict[int, Game] = {}
        self._game_cache_by_name: Dict[str, Game] = {}
        self.connect()

    def connect(self):
        """Initialize connection pool"""
        try:
            self.pool = ConnectionPool(
                conninfo=self.conninfo,
                min_size=2,
                max_size=self.pool_size,
                timeout=self.pool_timeout,
                kwargs={"row_factory": dict_row}
            )
            logger.info(f"Connected to PostgreSQL database: {self.database}")
        except Exception as e:
            logger.error(f"Error connecting to PostgreSQL: {e}")
            self.pool = None
            raise DatabaseConnectionError(f"Could not connect to database: {e}")

    def disconnect(self):
        """Close connection pool"""
        if self.pool:
            self.pool.close()
            logger.info("Database connection pool closed.")

    def get_connection(self):
        """Get a connection from the pool"""
        if not self.pool:
            raise DatabaseConnectionError("Connection pool not initialized")
        return self.pool.connection()

    def _cache_game(self, game: Optional[Game]) -> Optional[Game]:
        """Store a game row in both name/id caches."""
        if game is None:
            return None
        self._game_cache_by_id[game.game_id] = game
        self._game_cache_by_name[game.game_name] = game
        return game

    def _load_sql_asset(self, relative_path: str) -> None:
        """Execute an idempotent SQL asset file (functions/views) from the repo."""
        sql_path = Path(__file__).resolve().parent.parent / relative_path
        with sql_path.open("r", encoding="utf-8") as fh:
            sql_text = fh.read()
        with self.transaction() as cur:
            cur.execute(sql_text)

    def refresh_sql_assets(self) -> None:
        """Refresh SQL functions and views from the tracked asset files."""
        self._load_sql_asset("database/functions.sql")
        self._load_sql_asset("database/views.sql")

    def _load_schema_asset(self) -> None:
        """Execute the tracked schema file."""
        self._load_sql_asset("database/schema.sql")

    @contextmanager
    def transaction(self):
        """
        Transaction context manager.
        
        Usage:
            with db.transaction() as conn:
                cur = conn.cursor()
                cur.execute("INSERT ...")
                # Auto-commits on success, rolls back on exception
        """
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cur:
                    yield cur
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Transaction failed, rolled back: {e}")
                raise

    def _execute_query(
        self,
        query: str,
        params: Optional[Tuple] = None,
        fetchone: bool = False,
        fetchall: bool = False
    ):
        """
        Execute a query with automatic connection management.

        Args:
            query: SQL query string
            params: Query parameters tuple
            fetchone: Return single row
            fetchall: Return all rows

        Returns:
            Query result or None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(query, params or ())

                    if fetchone:
                        return cur.fetchone()
                    elif fetchall:
                        return cur.fetchall()
                    else:
                        conn.commit()
                        return None

                except Exception as e:
                    conn.rollback()
                    logger.warning(
                        f"Error executing query {query[:100]}... "
                        f"(params={params}, fetchone={fetchone}, fetchall={fetchall}): {e}"
                    )
                    raise

    # ========================================================================
    # USER OPERATIONS
    # ========================================================================

    def create_user(self, user_id: int, username: str = "Unknown", is_bot: bool = False):
        """Create a user record"""
        query = """
            INSERT INTO users (user_id, username, is_bot)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                username = EXCLUDED.username,
                is_bot = EXCLUDED.is_bot,
                updated_at = NOW();
        """
        self._execute_query(query, (user_id, username, is_bot))

    def get_user(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        query = "SELECT * FROM users WHERE user_id = %s;"
        result = self._execute_query(query, (user_id,), fetchone=True)
        return row_to_user(result) if result else None

    def update_user_preferences(self, user_id: int, preferences: Dict[str, Any]):
        """Update user preferences"""
        preferences_json = json.dumps(preferences)
        query = """
            INSERT INTO users (user_id, username, preferences)
            VALUES (%s, 'Unknown', %s::jsonb)
            ON CONFLICT (user_id) DO UPDATE SET
                preferences = EXCLUDED.preferences,
                updated_at = NOW();
        """
        self._execute_query(query, (user_id, preferences_json))

    def get_user_preferences(self, user_id: int) -> Optional[Dict]:
        """Get user preferences"""
        query = "SELECT created_at AS joined_at, preferences FROM users WHERE user_id = %s;"
        result = self._execute_query(query, (user_id,), fetchone=True)
        if result and result['preferences']:
            # Already a dict from dict_row
            return result
        return result

    def delete_user(self, user_id: int):
        """Delete a user (cascades to ratings, etc.)"""
        query = "DELETE FROM users WHERE user_id = %s;"
        self._execute_query(query, (user_id,))

    def search_users(self, query_text: str, limit: int = 10) -> List[User]:
        """Search users by username pattern"""
        query = """
            SELECT * FROM users
            WHERE username ILIKE %s AND is_active = TRUE
            LIMIT %s;
        """
        pattern = f"%{query_text}%"
        results = self._execute_query(query, (pattern, limit), fetchall=True)
        return [row_to_user(row) for row in results] if results else []

    # ========================================================================
    # GUILD OPERATIONS
    # ========================================================================

    def create_guild(self, guild_id: int, settings: Optional[Dict[str, Any]] = None):
        """Create a guild record"""
        settings_json = json.dumps(settings or {})
        query = """
            INSERT INTO guilds (guild_id, settings)
            VALUES (%s, %s::jsonb)
            ON CONFLICT (guild_id) DO UPDATE SET
                settings = EXCLUDED.settings,
                updated_at = NOW();
        """
        self._execute_query(query, (guild_id, settings_json))

    def get_guild(self, guild_id: int) -> Optional[Guild]:
        """Get guild by ID"""
        query = "SELECT * FROM guilds WHERE guild_id = %s;"
        result = self._execute_query(query, (guild_id,), fetchone=True)
        return row_to_guild(result) if result else None

    def update_guild_settings(self, guild_id: int, settings: Dict[str, Any]):
        """Update guild settings"""
        settings_json = json.dumps(settings)
        query = """
            INSERT INTO guilds (guild_id, settings)
            VALUES (%s, %s::jsonb)
            ON CONFLICT (guild_id) DO UPDATE SET
                settings = EXCLUDED.settings,
                updated_at = NOW();
        """
        self._execute_query(query, (guild_id, settings_json))

    def get_guild_settings(self, guild_id: int) -> Optional[Dict]:
        """Get guild settings"""
        query = "SELECT settings FROM guilds WHERE guild_id = %s;"
        result = self._execute_query(query, (guild_id,), fetchone=True)
        return result['settings'] if result else None

    def merge_guild_settings(self, guild_id: int, patch: Dict[str, Any]) -> None:
        """Merge JSON keys into guilds.settings (creates row if missing)."""
        self.create_guild(guild_id, {})
        query = """
            UPDATE guilds
            SET settings = COALESCE(settings, '{}'::jsonb) || %s::jsonb,
                updated_at = NOW()
            WHERE guild_id = %s;
        """
        self._execute_query(query, (json.dumps(patch), guild_id))

    def get_playcord_channel_id(self, guild_id: int) -> Optional[int]:
        s = self.get_guild_settings(guild_id)
        if not s:
            return None
        raw = s.get("playcord_channel_id")
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def delete_guild(self, guild_id: int):
        """Delete a guild (cascades to matches, ratings, etc.)"""
        query = "DELETE FROM guilds WHERE guild_id = %s;"
        self._execute_query(query, (guild_id,))

    def reset_user_data(self, user_id: int) -> None:
        """Delete all rows related to a user, then recreate a blank user shell."""
        self.delete_user(user_id)
        self.create_user(user_id, username="Unknown", is_bot=False)

    def reset_guild_data(self, guild_id: int) -> None:
        """Delete all rows related to a guild, then recreate an empty guild shell."""
        self.delete_guild(guild_id)
        self.create_guild(guild_id, settings={})

    def get_active_guilds(self) -> List[Guild]:
        """Get all active guilds"""
        query = "SELECT * FROM guilds WHERE is_active = TRUE ORDER BY created_at DESC;"
        results = self._execute_query(query, fetchall=True)
        return [row_to_guild(row) for row in results] if results else []

    # ========================================================================
    # GAME REGISTRY OPERATIONS
    # ========================================================================

    def register_game(
        self,
        game_name: str,
        display_name: str,
        min_players: int,
        max_players: int,
        rating_config: Dict[str, float],
        game_metadata: Optional[Dict[str, Any]] = None,
        game_schema_version: int = 1
    ) -> int:
        """Register a new game type (upsert from code definitions)."""
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
        result = self._execute_query(
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
            fetchone=True
        )
        game_id = result['game_id'] if result else None
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
                )
            )
        return game_id

    def _clamp_rating(self, mu: float, sigma: float, game_id: int) -> Tuple[float, float]:
        """Clamp mu/sigma using global config and per-game rating_config floors."""
        cfg = constants.CONFIGURATION.get("ratings", {})
        min_mu = float(cfg.get("min_mu", 0.0))
        min_sigma = float(cfg.get("min_sigma", 0.001))
        game = self._game_cache_by_id.get(game_id)
        if game is None:
            game = self.get_game_by_id(game_id)
        if game and game.rating_config:
            min_mu = float(game.rating_config.get("min_mu", min_mu))
            min_sigma = max(
                min_sigma,
                float(game.rating_config.get("min_sigma", min_sigma)),
            )
        min_sigma = max(min_sigma, 0.001)
        min_mu = max(min_mu, 0.0)
        return max(mu, min_mu), max(sigma, min_sigma)

    def sync_games_from_code(self) -> None:
        """Upsert all games from code-defined metadata and TrueSkill fractions."""
        import importlib

        from api.Game import resolve_player_count
        from configuration.constants import GAME_TYPES

        cfg = constants.CONFIGURATION.get("ratings", {})
        default_min_mu = float(cfg.get("min_mu", 0.0))
        default_min_sigma = float(cfg.get("min_sigma", 0.001))

        for game_name, (mod_name, cls_name) in GAME_TYPES.items():
            mod = importlib.import_module(mod_name)
            cls = getattr(mod, cls_name)
            display_name = getattr(cls, "name", game_name.replace("_", " ").title())
            spec = resolve_player_count(cls)
            if isinstance(spec, list):
                min_p, max_p = min(spec), max(spec)
            elif spec is None:
                min_p, max_p = 2, 2
            else:
                min_p = max_p = int(spec)
            ts = get_trueskill_parameters(game_name)
            def_sigma = float(ts["sigma"] * MU)
            rating_config = {
                "sigma": float(ts["sigma"] * MU),
                "beta": float(ts["beta"] * MU),
                "tau": float(ts["tau"] * MU),
                "draw": float(ts["draw"]),
                "default_mu": float(MU),
                "default_sigma": def_sigma,
                "min_mu": default_min_mu,
                "min_sigma": max(default_min_sigma, 0.001),
            }
            schema_ver = int(getattr(cls, "game_schema_version", 1))
            meta = {
                "summary": getattr(cls, "summary", ""),
                "description": getattr(cls, "description", ""),
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
        """Recompute matches_played from completed matches (repair drift)."""
        result = self._execute_query(
            "SELECT sync_games_played_counts() AS n;",
            fetchone=True,
        )
        return int(result["n"]) if result else 0

    def get_game(self, game_name: str) -> Optional[Game]:
        """Get game by name"""
        cached = self._game_cache_by_name.get(game_name)
        if cached is not None:
            return cached
        query = "SELECT * FROM games WHERE game_name = %s;"
        result = self._execute_query(query, (game_name,), fetchone=True)
        return self._cache_game(row_to_game(result) if result else None)

    def get_game_by_id(self, game_id: int) -> Optional[Game]:
        """Get game by ID"""
        cached = self._game_cache_by_id.get(game_id)
        if cached is not None:
            return cached
        query = "SELECT * FROM games WHERE game_id = %s;"
        result = self._execute_query(query, (game_id,), fetchone=True)
        return self._cache_game(row_to_game(result) if result else None)

    def get_all_games(self, active_only: bool = True) -> List[Game]:
        """Get all games"""
        if active_only:
            query = "SELECT * FROM games WHERE is_active = TRUE ORDER BY game_name;"
        else:
            query = "SELECT * FROM games ORDER BY game_name;"
        results = self._execute_query(query, fetchall=True)
        games = [row_to_game(row) for row in results] if results else []
        for game in games:
            self._cache_game(game)
        return games

    def update_game_config(self, game_id: int, config: Dict[str, Any]):
        """Update game rating configuration"""
        config_json = json.dumps(config)
        query = """
            UPDATE games SET rating_config = %s::jsonb, updated_at = NOW()
            WHERE game_id = %s;
        """
        self._execute_query(query, (config_json, game_id))

    def deactivate_game(self, game_id: int):
        """Deactivate a game"""
        query = "UPDATE games SET is_active = FALSE, updated_at = NOW() WHERE game_id = %s;"
        self._execute_query(query, (game_id,))

    def reset_game_data(self, game_id: int) -> Game:
        """Delete a game row and all cascaded data, then recreate the game from code definitions."""
        game = self.get_game_by_id(game_id)
        if game is None:
            raise ValueError(f"Game {game_id} not found")

        game_name = game.game_name
        self._execute_query("DELETE FROM games WHERE game_id = %s;", (game_id,))
        self._game_cache_by_id.pop(game_id, None)
        self._game_cache_by_name.pop(game_name, None)

        self.sync_games_from_code()
        recreated = self.get_game(game_name)
        if recreated is None:
            raise DatabaseError(f"Game {game_name!r} was deleted but not recreated from code")
        return recreated

    # ========================================================================
    # RATING OPERATIONS
    # ========================================================================

    def initialize_user_rating(self, user_id: int, game_id: int):
        """Ensure a rating row exists for this user and game (global, not per-guild)."""
        game = self.get_game_by_id(game_id)
        if not game:
            raise ValueError(f"Game {game_id} not found")

        mu = game.default_mu
        sigma = game.default_sigma

        query = """
            INSERT INTO user_game_ratings (user_id, game_id, mu, sigma)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, game_id) DO NOTHING;
        """
        self._execute_query(query, (user_id, game_id, mu, sigma))

    def get_user_rating(self, user_id: int, game_id: int) -> Optional[Rating]:
        """Get user rating for a specific game."""
        query = """
            SELECT * FROM user_game_ratings
            WHERE user_id = %s AND game_id = %s;
        """
        result = self._execute_query(query, (user_id, game_id), fetchone=True)
        return row_to_rating(result) if result else None

    def get_user_all_ratings(self, user_id: int) -> List[Rating]:
        """Get all game ratings for a user."""
        query = """
            SELECT * FROM user_game_ratings
            WHERE user_id = %s
            ORDER BY game_id;
        """
        results = self._execute_query(query, (user_id,), fetchall=True)
        return [row_to_rating(row) for row in results] if results else []

    def update_rating(
        self,
        user_id: int,
        game_id: int,
        mu: float,
        sigma: float,
        matches_increment: int = 1,
    ):
        """Update user rating after a match (W/L/D derived from match_participants when needed)."""
        mu, sigma = self._clamp_rating(mu, sigma, game_id)
        query = """
            UPDATE user_game_ratings
            SET mu = %s,
                sigma = %s,
                matches_played = matches_played + %s,
                last_played = NOW(),
                updated_at = NOW()
            WHERE user_id = %s AND game_id = %s;
        """
        self._execute_query(
            query,
            (mu, sigma, matches_increment, user_id, game_id)
        )

    def bulk_update_ratings(self, updates: List[Dict[str, Any]]):
        """Bulk update multiple ratings in a transaction"""
        with self.transaction() as cur:
            for update in updates:
                matches_increment = int(update.get("matches_increment", 1))
                query = """
                    UPDATE user_game_ratings
                    SET mu = %s, sigma = %s, matches_played = matches_played + %s,
                        last_played = NOW(), updated_at = NOW()
                    WHERE user_id = %s AND game_id = %s;
                """
                mu_c, sig_c = self._clamp_rating(
                    update['mu'], update['sigma'], update['game_id']
                )
                cur.execute(
                    query,
                    (mu_c, sig_c, matches_increment, update['user_id'], update['game_id'])
                )

    def reset_user_rating(self, user_id: int, game_id: int):
        """Reset user rating to defaults"""
        game = self.get_game_by_id(game_id)
        if not game:
            raise ValueError(f"Game {game_id} not found")

        query = """
            UPDATE user_game_ratings
            SET mu = %s,
                sigma = %s,
                matches_played = 0,
                last_played = NULL,
                last_sigma_increase = NULL,
                updated_at = NOW()
            WHERE user_id = %s AND game_id = %s;
        """
        self._execute_query(
            query,
            (game.default_mu, game.default_sigma, user_id, game_id)
        )

    def delete_user_rating(self, user_id: int, game_id: int):
        """Delete user rating"""
        query = """
            DELETE FROM user_game_ratings
            WHERE user_id = %s AND game_id = %s;
        """
        self._execute_query(query, (user_id, game_id))

    # ========================================================================
    # LEADERBOARD OPERATIONS
    # ========================================================================

    def get_leaderboard(
        self,
        member_user_ids: List[int],
        game_id: int,
        limit: int = 10,
        offset: int = 0,
        min_matches: int = 5
    ) -> List[Dict[str, Any]]:
        """Guild/server leaderboard: same global ratings, filtered to guild members."""
        if not member_user_ids:
            return []
        query = """
            SELECT 
                ugr.user_id,
                u.username,
                ugr.mu,
                ugr.sigma,
                (ugr.mu - 3 * ugr.sigma) as conservative_rating,
                ugr.matches_played
            FROM user_game_ratings ugr
            JOIN users u ON ugr.user_id = u.user_id
            WHERE ugr.game_id = %s
              AND ugr.user_id = ANY(%s::bigint[])
              AND ugr.matches_played >= %s
            ORDER BY conservative_rating DESC
            LIMIT %s OFFSET %s;
        """
        results = self._execute_query(
            query,
            (game_id, member_user_ids, min_matches, limit, offset),
            fetchall=True
        )
        return results if results else []

    def get_global_leaderboard(
        self,
        game_id: int,
        limit: int = 10,
        offset: int = 0,
        min_matches: int = 10
    ) -> List[Dict[str, Any]]:
        """Global leaderboard (all users with a rating row for this game)."""
        query = """
            SELECT 
                ugr.user_id,
                u.username,
                ugr.mu,
                ugr.sigma,
                (ugr.mu - 3 * ugr.sigma) as conservative_rating,
                ugr.matches_played
            FROM user_game_ratings ugr
            JOIN users u ON ugr.user_id = u.user_id
            WHERE ugr.game_id = %s
              AND ugr.matches_played >= %s
            ORDER BY conservative_rating DESC
            LIMIT %s OFFSET %s;
        """
        results = self._execute_query(query, (game_id, min_matches, limit, offset), fetchall=True)
        return results if results else []

    def get_user_rank(
        self,
        user_id: int,
        member_user_ids: List[int],
        game_id: int,
        min_matches: int = 5,
    ) -> int:
        """Rank among guild members for this game (1-based), or -1 if unranked."""
        if not member_user_ids:
            return -1
        query = """
            WITH ranked AS (
                SELECT 
                    user_id,
                    ROW_NUMBER() OVER (ORDER BY (mu - 3 * sigma) DESC) as rank
                FROM user_game_ratings
                WHERE game_id = %s
                  AND user_id = ANY(%s::bigint[])
                  AND matches_played >= %s
            )
            SELECT rank FROM ranked WHERE user_id = %s;
        """
        result = self._execute_query(
            query, (game_id, member_user_ids, min_matches, user_id), fetchone=True
        )
        return result['rank'] if result else -1

    def get_user_global_rank(self, user_id: int, game_id: int, min_matches: int = 5) -> Optional[int]:
        """
        Get user's global rank for a specific game.

        :param user_id: Discord user ID
        :param game_id: Game ID
        :param min_matches: Minimum matches required to be ranked
        :return: Global rank position (1-indexed) or None if not ranked
        """
        query = """
            WITH ranked AS (
                SELECT 
                    user_id,
                    ROW_NUMBER() OVER (ORDER BY (mu - 3 * sigma) DESC) as rank
                FROM user_game_ratings
                WHERE game_id = %s
                  AND matches_played >= %s
            )
            SELECT rank FROM ranked WHERE user_id = %s;
        """
        result = self._execute_query(query, (game_id, min_matches, user_id), fetchone=True)
        return result['rank'] if result else None

    def get_global_player_count(self, game_id: int, min_matches: int = 5) -> int:
        """
        Get total number of ranked players globally for a game.

        :param game_id: Game ID
        :param min_matches: Minimum matches required to be ranked
        :return: Total ranked player count
        """
        query = """
            SELECT COUNT(*) as count
            FROM user_game_ratings
            WHERE game_id = %s
              AND matches_played >= %s;
        """
        result = self._execute_query(query, (game_id, min_matches), fetchone=True)
        return result['count'] if result else 0

    # ========================================================================
    # MATCH OPERATIONS
    # ========================================================================

    def create_match(
        self,
        game_id: int,
        guild_id: int,
        channel_id: int,
        thread_id: Optional[int],
        participants: List[int],  # List of user IDs
        is_rated: bool = True,
        game_config: Optional[Dict[str, Any]] = None
    ) -> Tuple[int, str]:
        """
        Create a new match and initialize participants.
        Returns (match_id, match_code) with a unique 8-character public ``match_code``.
        """
        self.create_guild(guild_id)

        # Ensure all users exist and have ratings
        for user_id in participants:
            self.create_user(user_id)
            self.initialize_user_rating(user_id, game_id)

        config_json = json.dumps(game_config or {})

        last_err: Optional[Exception] = None
        for _ in range(48):
            match_code = generate_match_code()
            try:
                with self.transaction() as cur:
                    cur.execute(
                        """
                        INSERT INTO matches (game_id, guild_id, channel_id, thread_id,
                            is_rated, game_config, status, match_code)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'in_progress', %s)
                        RETURNING match_id;
                        """,
                        (
                            game_id,
                            guild_id,
                            channel_id,
                            thread_id,
                            is_rated,
                            config_json,
                            match_code,
                        ),
                    )
                    result = cur.fetchone()
                    match_id = result["match_id"]

                    for idx, user_id in enumerate(participants, start=1):
                        cur.execute(
                            """
                            SELECT mu, sigma
                            FROM user_game_ratings
                            WHERE user_id = %s AND game_id = %s
                            FOR SHARE;
                            """,
                            (user_id, game_id),
                        )
                        rating = cur.fetchone()
                        mu_before = rating["mu"] if rating else MU
                        sigma_before = rating["sigma"] if rating else (MU / 3)

                        cur.execute(
                            """
                            INSERT INTO match_participants
                                (match_id, user_id, player_number, mu_before, sigma_before)
                            VALUES (%s, %s, %s, %s, %s);
                            """,
                            (match_id, user_id, idx, mu_before, sigma_before),
                        )

                return match_id, match_code
            except pg_errors.UniqueViolation as e:
                last_err = e
                continue

        raise RuntimeError("Could not allocate a unique match_code") from last_err

    def get_match_by_code(self, code: str) -> Optional[Match]:
        """Resolve a match by its public ``match_code`` (case-insensitive)."""
        c = (code or "").strip().lower()
        if not c:
            return None
        query = "SELECT * FROM matches WHERE lower(match_code) = %s;"
        result = self._execute_query(query, (c,), fetchone=True)
        return row_to_match(result) if result else None

    def get_match(self, match_id: int) -> Optional[Match]:
        """Get match by ID"""
        query = "SELECT * FROM matches WHERE match_id = %s;"
        result = self._execute_query(query, (match_id,), fetchone=True)
        return row_to_match(result) if result else None

    def update_match_status(self, match_id: int, status: str):
        """Update match status"""
        query = "UPDATE matches SET status = %s WHERE match_id = %s;"
        self._execute_query(query, (status, match_id))

    def merge_match_metadata_outcome_display(
        self,
        match_id: int,
        *,
        summaries: dict[int, str] | None = None,
        global_summary: str | None = None,
    ) -> None:
        """
        Store outcome_global_summary (single line) and/or outcome_summaries (per user id) on matches.metadata.
        """
        patch: dict[str, Any] = {}
        if global_summary and str(global_summary).strip():
            patch["outcome_global_summary"] = str(global_summary).strip()
        if summaries is not None:
            patch["outcome_summaries"] = {str(uid): text for uid, text in summaries.items()}
        if not patch:
            return
        payload = json.dumps(patch)
        query = """
            UPDATE matches
            SET metadata = (COALESCE(metadata, '{}'::jsonb) - 'outcome_summary')
                || %s::jsonb
            WHERE match_id = %s;
        """
        self._execute_query(query, (payload, match_id))

    def get_match_human_user_ids_ordered(self, match_id: int) -> List[int]:
        """Participant Discord user IDs for a match, excluding bot accounts, in seat order."""
        query = """
            SELECT mp.user_id
            FROM match_participants mp
            JOIN users u ON u.user_id = mp.user_id
            WHERE mp.match_id = %s AND u.is_bot = FALSE
            ORDER BY mp.player_number;
        """
        rows = self._execute_query(query, (match_id,), fetchall=True) or []
        return [int(r["user_id"]) for r in rows]

    def update_match_context(
        self,
        match_id: int,
        channel_id: Optional[int] = None,
        thread_id: Optional[int] = None
    ):
        """Update channel/thread identifiers for an existing match."""
        updates = []
        params = []
        if channel_id is not None:
            updates.append("channel_id = %s")
            params.append(channel_id)
        if thread_id is not None:
            updates.append("thread_id = %s")
            params.append(thread_id)

        if not updates:
            return

        params.append(match_id)
        query = f"UPDATE matches SET {', '.join(updates)} WHERE match_id = %s;"
        self._execute_query(query, tuple(params))

    def end_match(
        self,
        match_id: int,
        final_state: Dict[str, Any],
        results: Dict[int, Dict[str, Any]]  # user_id -> {ranking, mu_delta, sigma_delta, ...}
    ):
        """
        End a match with final results and update ratings.
        This is a transactional operation.
        
        Args:
            match_id: Match ID
            final_state: Final game state
            results: Dict mapping user_id to result data:
                     {ranking, mu_delta, sigma_delta, new_mu, new_sigma}
        """
        final_state_json = json.dumps(final_state)

        with self.transaction() as cur:
            cur.execute(
                """
                SELECT game_id, guild_id, status
                FROM matches
                WHERE match_id = %s
                FOR UPDATE;
                """,
                (match_id,),
            )
            match = cur.fetchone()
            if not match:
                raise ValueError(f"Match {match_id} not found")
            if match["status"] == MatchStatus.COMPLETED.value:
                raise ValueError(f"Match {match_id} is already completed")

            # Update participants and ratings
            for user_id, result in results.items():
                # Update participant
                cur.execute(
                    """
                    UPDATE match_participants
                    SET final_ranking = %s,
                        score = %s,
                        mu_delta = %s,
                        sigma_delta = %s
                    WHERE match_id = %s AND user_id = %s;
                    """,
                    (
                        result['ranking'],
                        result.get('score'),
                        result['mu_delta'],
                        result['sigma_delta'],
                        match_id,
                        user_id
                    )
                )

                new_mu, new_sigma = self._clamp_rating(
                    result['new_mu'], result['new_sigma'], match["game_id"]
                )

                # Update rating
                cur.execute(
                    """
                    UPDATE user_game_ratings
                    SET mu = %s,
                        sigma = %s,
                        updated_at = NOW()
                    WHERE user_id = %s AND game_id = %s;
                    """,
                    (
                        new_mu,
                        new_sigma,
                        user_id,
                        match["game_id"]
                    )
                )

                # Record rating history
                cur.execute(
                    """
                    INSERT INTO rating_history
                        (user_id, guild_id, game_id, match_id,
                         mu_before, sigma_before, mu_after, sigma_after)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    (
                        user_id,
                        match["guild_id"],
                        match["game_id"],
                        match_id,
                        result.get('mu_before', new_mu - result['mu_delta']),
                        result.get('sigma_before', new_sigma - result['sigma_delta']),
                        new_mu,
                        new_sigma
                    )
                )

            cur.execute(
                """
                UPDATE matches
                SET status = 'completed',
                    ended_at = NOW(),
                    final_state = %s::jsonb,
                    updated_at = NOW()
                WHERE match_id = %s;
                """,
                (final_state_json, match_id)
            )

    def delete_match(self, match_id: int):
        """Delete a match (cascades to participants and moves)"""
        query = "DELETE FROM matches WHERE match_id = %s;"
        self._execute_query(query, (match_id,))

    def get_active_matches(self, guild_id: Optional[int] = None) -> List[Match]:
        """Get active (in-progress) matches"""
        if guild_id is not None:
            query = """
                SELECT * FROM matches
                WHERE status = 'in_progress' AND guild_id = %s
                ORDER BY started_at DESC;
            """
            results = self._execute_query(query, (guild_id,), fetchall=True)
        else:
            query = """
                SELECT * FROM matches
                WHERE status = 'in_progress'
                ORDER BY started_at DESC;
            """
            results = self._execute_query(query, fetchall=True)

        return [row_to_match(row) for row in results] if results else []

    def get_recent_matches(
        self,
        guild_id: int,
        game_id: int,
        limit: int = 10
    ) -> List[Match]:
        """Get recent completed matches"""
        query = """
            SELECT * FROM matches
            WHERE guild_id = %s AND game_id = %s AND status = 'completed'
            ORDER BY ended_at DESC
            LIMIT %s;
        """
        results = self._execute_query(query, (guild_id, game_id, limit), fetchall=True)
        return [row_to_match(row) for row in results] if results else []

    def abandon_match(self, match_id: int, reason: str):
        """Mark a match as abandoned"""
        metadata = json.dumps({"abandon_reason": reason})
        query = """
            UPDATE matches
            SET status = 'abandoned',
                ended_at = NOW(),
                metadata = jsonb_set(COALESCE(metadata, '{}'::jsonb), '{abandon_reason}', %s::jsonb)
            WHERE match_id = %s;
        """
        self._execute_query(query, (f'"{reason}"', match_id))

    # ========================================================================
    # PARTICIPANT OPERATIONS
    # ========================================================================

    def add_participant(
        self,
        match_id: int,
        user_id: int,
        player_number: int,
        mu_before: Optional[float] = None,
        sigma_before: Optional[float] = None
    ):
        """Add a participant to a match"""
        query = """
            INSERT INTO match_participants
                (match_id, user_id, player_number, mu_before, sigma_before)
            VALUES (%s, %s, %s, %s, %s);
        """
        self._execute_query(query, (match_id, user_id, player_number, mu_before, sigma_before))

    def get_participants(self, match_id: int) -> List[Participant]:
        """Get all participants for a match"""
        query = """
            SELECT * FROM match_participants
            WHERE match_id = %s
            ORDER BY player_number;
        """
        results = self._execute_query(query, (match_id,), fetchall=True)
        return [row_to_participant(row) for row in results] if results else []

    def update_participant_result(
        self,
        participant_id: int,
        ranking: int,
        score: Optional[float],
        mu_delta: float,
        sigma_delta: float
    ):
        """Update participant result"""
        query = """
            UPDATE match_participants
            SET final_ranking = %s,
                score = %s,
                mu_delta = %s,
                sigma_delta = %s
            WHERE participant_id = %s;
        """
        self._execute_query(query, (ranking, score, mu_delta, sigma_delta, participant_id))

    def remove_participant(self, match_id: int, user_id: int):
        """Remove a participant from a match"""
        query = "DELETE FROM match_participants WHERE match_id = %s AND user_id = %s;"
        self._execute_query(query, (match_id, user_id))

    # ========================================================================
    # MOVE HISTORY OPERATIONS
    # ========================================================================

    def record_move(
        self,
        match_id: int,
        user_id: Optional[int],
        move_number: int,
        move_data: Dict[str, Any],
        game_state_after: Optional[Dict[str, Any]] = None,
        time_taken_ms: Optional[int] = None,
        is_game_affecting: bool = True
    ):
        """Record a move in a match"""
        move_json = json.dumps(move_data)
        state_json = json.dumps(game_state_after) if game_state_after else None

        query = """
            INSERT INTO moves
                (match_id, user_id, move_number, move_data, game_state_after,
                 time_taken_ms, is_game_affecting)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s);
        """
        self._execute_query(
            query,
            (
                match_id,
                user_id,
                move_number,
                move_json,
                state_json,
                time_taken_ms,
                is_game_affecting,
            )
        )

    def append_replay_event(self, match_id: int, event: Dict[str, Any]) -> None:
        """
        Append one structured replay event to ``replay_events``.
        ``type`` is normalized into ``event_type`` and ``user_id`` into ``actor_user_id``.
        """
        payload = dict(event or {})
        event_type = str(payload.pop("type", "event"))
        actor_user_id = payload.pop("user_id", None)
        if actor_user_id is not None:
            try:
                actor_user_id = int(actor_user_id)
            except (TypeError, ValueError):
                actor_user_id = None
        with self.transaction() as cur:
            cur.execute("SELECT 1 FROM matches WHERE match_id = %s FOR UPDATE;", (match_id,))
            cur.execute(
                """
                SELECT COALESCE(MAX(sequence_number), 0) + 1 AS next_sequence
                FROM replay_events
                WHERE match_id = %s;
                """,
                (match_id,),
            )
            next_sequence = cur.fetchone()["next_sequence"]
            cur.execute(
                """
                INSERT INTO replay_events (
                    match_id, sequence_number, event_type, actor_user_id, payload
                )
                VALUES (%s, %s, %s, %s, %s::jsonb);
                """,
                (
                    match_id,
                    next_sequence,
                    event_type,
                    actor_user_id,
                    json.dumps(payload),
                ),
            )

    def get_replay_events(self, match_id: int) -> List[Dict[str, Any]]:
        """Return replay events in order from the canonical ``replay_events`` table."""
        rows = self._execute_query(
            """
            SELECT event_type, actor_user_id, payload
            FROM replay_events
            WHERE match_id = %s
            ORDER BY sequence_number ASC;
            """,
            (match_id,),
            fetchall=True,
        ) or []
        events: List[Dict[str, Any]] = []
        for row in rows:
            payload = dict(row.get("payload") or {})
            payload["type"] = row["event_type"]
            if row.get("actor_user_id") is not None and "user_id" not in payload:
                payload["user_id"] = row["actor_user_id"]
            events.append(payload)
        return events

    def get_match_moves(self, match_id: int) -> List[Move]:
        """Get all moves for a match in order"""
        query = """
            SELECT * FROM moves
            WHERE match_id = %s
            ORDER BY move_number ASC;
        """
        results = self._execute_query(query, (match_id,), fetchall=True)
        return [row_to_move(row) for row in results] if results else []

    def get_move_count(self, match_id: int) -> int:
        """Get number of moves in a match"""
        query = "SELECT COUNT(*) as count FROM moves WHERE match_id = %s;"
        result = self._execute_query(query, (match_id,), fetchone=True)
        return result['count'] if result else 0

    def validate_move_sequence(self, match_id: int) -> bool:
        """Check if move sequence is valid (no gaps)"""
        query = """
            SELECT 
                COUNT(*) as move_count,
                MAX(move_number) as max_move
            FROM moves
            WHERE match_id = %s;
        """
        result = self._execute_query(query, (match_id,), fetchone=True)
        if not result:
            return True
        return result['move_count'] == result['max_move'] or result['move_count'] == 0

    # ========================================================================
    # USER HISTORY & STATS
    # ========================================================================

    def get_user_match_history(
        self,
        user_id: int,
        guild_id: Optional[int],
        game_id: Optional[int] = None,
        limit: int = 10,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get user's match history"""
        query = """
            SELECT 
                m.match_id,
                m.match_code,
                m.game_id,
                g.game_name as game_key,
                g.display_name as game_name,
                m.ended_at,
                m.is_rated,
                m.metadata,
                mp.final_ranking as final_ranking,
                mp.player_number,
                COUNT(*) OVER (PARTITION BY m.match_id) as player_count,
                mp.mu_delta,
                mp.sigma_delta
            FROM match_participants mp
            JOIN matches m ON mp.match_id = m.match_id
            JOIN games g ON m.game_id = g.game_id
            WHERE mp.user_id = %s
              AND m.status = 'completed'
        """
        params: List[Any] = [user_id]
        if guild_id is not None:
            query += " AND m.guild_id = %s"
            params.append(guild_id)
        if game_id is not None:
            query += " AND m.game_id = %s"
            params.append(game_id)

        query += """
            ORDER BY m.ended_at DESC
            LIMIT %s OFFSET %s;
        """
        params.extend([limit, offset])
        results = self._execute_query(query, tuple(params), fetchall=True)
        return results if results else []

    def get_head_to_head(
        self,
        user1_id: int,
        user2_id: int,
        game_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get head-to-head stats between two players"""
        if game_id is not None:
            query = """
                SELECT 
                    m.game_id,
                    g.display_name as game_name,
                    COUNT(*) as total_matches,
                    SUM(CASE WHEN mp1.final_ranking < mp2.final_ranking THEN 1 ELSE 0 END) as user1_wins,
                    SUM(CASE WHEN mp2.final_ranking < mp1.final_ranking THEN 1 ELSE 0 END) as user2_wins,
                    SUM(CASE WHEN mp1.final_ranking = mp2.final_ranking THEN 1 ELSE 0 END) as draws,
                    MAX(m.ended_at) as last_match_date
                FROM matches m
                JOIN games g ON m.game_id = g.game_id
                JOIN match_participants mp1 ON m.match_id = mp1.match_id AND mp1.user_id = %s
                JOIN match_participants mp2 ON m.match_id = mp2.match_id AND mp2.user_id = %s
                WHERE m.status = 'completed' AND m.game_id = %s
                GROUP BY m.game_id, g.display_name;
            """
            results = self._execute_query(query, (user1_id, user2_id, game_id), fetchall=True)
        else:
            query = """
                SELECT 
                    m.game_id,
                    g.display_name as game_name,
                    COUNT(*) as total_matches,
                    SUM(CASE WHEN mp1.final_ranking < mp2.final_ranking THEN 1 ELSE 0 END) as user1_wins,
                    SUM(CASE WHEN mp2.final_ranking < mp1.final_ranking THEN 1 ELSE 0 END) as user2_wins,
                    SUM(CASE WHEN mp1.final_ranking = mp2.final_ranking THEN 1 ELSE 0 END) as draws,
                    MAX(m.ended_at) as last_match_date
                FROM matches m
                JOIN games g ON m.game_id = g.game_id
                JOIN match_participants mp1 ON m.match_id = mp1.match_id AND mp1.user_id = %s
                JOIN match_participants mp2 ON m.match_id = mp2.match_id AND mp2.user_id = %s
                WHERE m.status = 'completed'
                GROUP BY m.game_id, g.display_name
                ORDER BY total_matches DESC;
            """
            results = self._execute_query(query, (user1_id, user2_id), fetchall=True)

        return results if results else []

    def get_user_stats(
        self,
        user_id: int,
        game_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get comprehensive user statistics (global per-game rating)."""
        query = """
            SELECT 
                ugr.*,
                u.username,
                g.display_name as game_name,
                (ugr.mu - 3 * ugr.sigma) as conservative_rating
            FROM user_game_ratings ugr
            JOIN users u ON ugr.user_id = u.user_id
            JOIN games g ON ugr.game_id = g.game_id
            WHERE ugr.user_id = %s
              AND ugr.game_id = %s;
        """
        result = self._execute_query(query, (user_id, game_id), fetchone=True)
        return result

    def get_rating_history(
        self,
        user_id: int,
        guild_id: Optional[int],
        game_id: int,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get rating history for a user"""
        query = """
            SELECT 
                history_id,
                match_id,
                mu_before,
                sigma_before,
                mu_after,
                sigma_after,
                (mu_after - mu_before) as mu_delta,
                (sigma_after - sigma_before) as sigma_delta,
                created_at
            FROM rating_history
            WHERE user_id = %s
              AND game_id = %s
              AND created_at > NOW() - (%s * INTERVAL '1 day')
        """
        params: List[Any] = [user_id, game_id, days]
        if guild_id is not None:
            query += " AND guild_id = %s"
            params.append(guild_id)
        query += """
            ORDER BY created_at DESC;
        """
        results = self._execute_query(query, tuple(params), fetchall=True)
        return results if results else []

    # ========================================================================
    # ANALYTICS OPERATIONS
    # ========================================================================

    def record_event(
        self,
        event_type: str,
        user_id: Optional[int] = None,
        guild_id: Optional[int] = None,
        game_id: Optional[int] = None,
        match_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Record an analytics event"""
        if user_id:
            self.create_user(user_id)
        if guild_id:
            self.create_guild(guild_id)

        metadata_json = json.dumps(metadata) if metadata else None
        query = """
            INSERT INTO analytics_events
                (event_type, user_id, guild_id, game_id, match_id, metadata)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb);
        """
        self._execute_query(
            query,
            (event_type, user_id, guild_id, game_id, match_id, metadata_json)
        )

    def get_events(
        self,
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get analytics events with optional filters"""
        conditions = []
        params = []

        if event_type:
            conditions.append("event_type = %s")
            params.append(event_type)

        if start_date:
            conditions.append("created_at >= %s")
            params.append(start_date)

        if end_date:
            conditions.append("created_at <= %s")
            params.append(end_date)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        query = f"""
            SELECT * FROM analytics_events
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s;
        """
        results = self._execute_query(query, tuple(params), fetchall=True)
        return results if results else []

    def get_user_events(self, user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """Get events for a specific user"""
        query = """
            SELECT * FROM analytics_events
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s;
        """
        results = self._execute_query(query, (user_id, limit), fetchall=True)
        return results if results else []

    def get_guild_analytics(self, guild_id: int, days: int = 30) -> Dict[str, Any]:
        """Get analytics summary for a guild"""
        query = """
            SELECT 
                COUNT(DISTINCT user_id) as active_users,
                COUNT(DISTINCT CASE WHEN event_type = 'game_started' THEN event_id END) as games_started,
                COUNT(DISTINCT CASE WHEN event_type = 'game_completed' THEN event_id END) as games_completed,
                COUNT(DISTINCT CASE WHEN event_type = 'command_used' THEN event_id END) as commands_used
            FROM analytics_events
            WHERE guild_id = %s
              AND created_at > NOW() - (%s * INTERVAL '1 day');
        """
        result = self._execute_query(query, (guild_id, days), fetchone=True)
        return result if result else {}

    def get_analytics_event_counts(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Count analytics rows by event_type in the last N hours."""
        query = """
            SELECT event_type, COUNT(*)::BIGINT AS cnt
            FROM analytics_events
            WHERE created_at > NOW() - (%s * INTERVAL '1 hour')
            GROUP BY event_type
            ORDER BY cnt DESC;
        """
        rows = self._execute_query(query, (hours,), fetchall=True)
        return rows if rows else []

    def get_analytics_recent_events(self, hours: int = 24, limit: int = 60) -> List[Dict[str, Any]]:
        """Recent analytics rows with ids and metadata for operator review."""
        query = """
            SELECT event_id, event_type, created_at, user_id, guild_id, game_id, match_id, metadata
            FROM analytics_events
            WHERE created_at > NOW() - (%s * INTERVAL '1 hour')
            ORDER BY created_at DESC
            LIMIT %s;
        """
        rows = self._execute_query(query, (hours, limit), fetchall=True)
        return rows if rows else []

    def get_analytics_event_counts_by_game(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Count rows by game slug in the last N hours (via analytics_events.game_id -> games.game_name)."""
        query = """
            SELECT g.game_name AS game_type, COUNT(*)::BIGINT AS cnt
            FROM analytics_events ae
            INNER JOIN games g ON g.game_id = ae.game_id
            WHERE ae.created_at > NOW() - (%s * INTERVAL '1 hour')
            GROUP BY g.game_name
            ORDER BY cnt DESC;
        """
        rows = self._execute_query(query, (hours,), fetchall=True)
        return rows if rows else []

    # ========================================================================
    # MAINTENANCE OPERATIONS
    # ========================================================================

    def apply_skill_decay(
        self,
        days_inactive: int = 30,
        sigma_increase: float = 0.1
    ) -> int:
        """Apply skill decay to inactive players"""
        query = """
            UPDATE user_game_ratings
            SET sigma = sigma * (1 + %s),
                last_sigma_increase = NOW(),
                updated_at = NOW()
            WHERE last_played < NOW() - (%s * INTERVAL '1 day')
              AND (last_sigma_increase IS NULL 
                   OR last_sigma_increase < NOW() - (%s * INTERVAL '1 day'))
            RETURNING user_id;
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (sigma_increase, days_inactive, days_inactive))
                results = cur.fetchall()
                conn.commit()
                return len(results) if results else 0

    def cleanup_old_analytics(self, days: int = 90) -> int:
        """Delete old analytics events"""
        query = """
            DELETE FROM analytics_events
            WHERE created_at < NOW() - (%s * INTERVAL '1 day');
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (days,))
                count = cur.rowcount
                conn.commit()
                return count

    def get_inactive_users(self, guild_id: int, days: int = 30) -> List[Dict[str, Any]]:
        """Users who played in this guild and have a stale global last_played for some game."""
        query = """
            SELECT DISTINCT
                ugr.user_id,
                u.username,
                ugr.game_id,
                ugr.last_played,
                EXTRACT(EPOCH FROM (NOW() - ugr.last_played))::INTEGER / 86400 as days_inactive
            FROM user_game_ratings ugr
            JOIN users u ON ugr.user_id = u.user_id
            WHERE ugr.user_id IN (
                SELECT DISTINCT mp.user_id
                FROM match_participants mp
                JOIN matches m ON mp.match_id = m.match_id
                WHERE m.guild_id = %s AND m.status = 'completed'
            )
              AND ugr.last_played < NOW() - (%s * INTERVAL '1 day')
            ORDER BY ugr.last_played ASC;
        """
        results = self._execute_query(query, (guild_id, days), fetchall=True)
        return results if results else []

    def archive_old_matches(self, days: int = 365) -> int:
        """Archive old matches by marking in metadata"""
        metadata_update = json.dumps(True)
        query = """
            UPDATE matches
            SET metadata = jsonb_set(
                COALESCE(metadata, '{}'::jsonb),
                '{archived}',
                %s::jsonb
            )
            WHERE ended_at < NOW() - (%s * INTERVAL '1 day')
              AND status = 'completed'
              AND NOT (metadata ? 'archived' AND (metadata->>'archived')::boolean = true)
            RETURNING match_id;
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (metadata_update, days))
                results = cur.fetchall()
                conn.commit()
                return len(results) if results else 0

    def vacuum_analyze(self):
        """Run VACUUM ANALYZE for database maintenance"""
        # Must be run outside a transaction
        with self.get_connection() as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("VACUUM ANALYZE;")
            conn.autocommit = False

    def reset_all_data(self) -> None:
        """Drop and recreate the entire public schema, then rebuild tracked DB assets."""
        self._game_cache_by_id.clear()
        self._game_cache_by_name.clear()
        with self.get_connection() as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("DROP SCHEMA IF EXISTS public CASCADE;")
                cur.execute("CREATE SCHEMA public;")
            conn.autocommit = False

        self._load_schema_asset()
        db_migrations.apply_migrations(self)
        self.refresh_sql_assets()
        self.sync_games_from_code()

    # ========================================================================
    # GLOBAL RATING OPERATIONS
    # ========================================================================

    def calculate_global_ratings(self, game_id: int) -> int:
        """No-op count: ratings are stored only in user_game_ratings (game_id kept for API compatibility)."""
        return 0

    # ========================================================================
    # AGGREGATION & REPORTS
    # ========================================================================

    def get_match_count_by_game(self, guild_id: int, days: int = 30) -> Dict[str, int]:
        """Get match counts by game type"""
        query = """
            SELECT 
                g.display_name as game_name,
                COUNT(*) as match_count
            FROM matches m
            JOIN games g ON m.game_id = g.game_id
            WHERE m.guild_id = %s
              AND m.ended_at > NOW() - (%s * INTERVAL '1 day')
              AND m.status = 'completed'
            GROUP BY g.display_name
            ORDER BY match_count DESC;
        """
        results = self._execute_query(query, (guild_id, days), fetchall=True)
        return {row['game_name']: row['match_count'] for row in results} if results else {}

    def get_player_retention(self, guild_id: int, days: int = 7) -> float:
        """Share of distinct users who completed a match in this guild recently vs. ever."""
        query = """
            WITH guild_users AS (
                SELECT DISTINCT mp.user_id
                FROM match_participants mp
                JOIN matches m ON mp.match_id = m.match_id
                WHERE m.guild_id = %s AND m.status = 'completed'
            ),
            active_players AS (
                SELECT COUNT(DISTINCT mp.user_id) as count
                FROM match_participants mp
                JOIN matches m ON mp.match_id = m.match_id
                WHERE m.guild_id = %s
                  AND m.status = 'completed'
                  AND m.ended_at > NOW() - (%s * INTERVAL '1 day')
            ),
            total_players AS (
                SELECT COUNT(*)::BIGINT as count FROM guild_users
            )
            SELECT 
                CASE 
                    WHEN total_players.count > 0
                    THEN (active_players.count::FLOAT / total_players.count::FLOAT) * 100.0
                    ELSE 0.0
                END as retention_rate
            FROM active_players, total_players;
        """
        result = self._execute_query(query, (guild_id, guild_id, days), fetchone=True)
        return result['retention_rate'] if result else 0.0

    def get_most_active_players(
        self,
        guild_id: int,
        game_id: int,
        days: int = 7,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get most active players"""
        query = """
            SELECT 
                u.user_id,
                u.username,
                COUNT(DISTINCT m.match_id) as match_count
            FROM match_participants mp
            JOIN matches m ON mp.match_id = m.match_id
            JOIN users u ON mp.user_id = u.user_id
            WHERE m.guild_id = %s
              AND m.game_id = %s
              AND m.ended_at > NOW() - (%s * INTERVAL '1 day')
              AND m.status = 'completed'
            GROUP BY u.user_id, u.username
            ORDER BY match_count DESC
            LIMIT %s;
        """
        results = self._execute_query(query, (guild_id, game_id, days, limit), fetchall=True)
        return results if results else []

    # ========================================================================
    # UTILITY OPERATIONS
    # ========================================================================

    def count_matches(
        self,
        guild_id: int,
        game_id: int,
        is_rated: Optional[bool] = None
    ) -> int:
        """Count matches for a game in a guild"""
        if is_rated is not None:
            query = """
                SELECT COUNT(*) as count FROM matches
                WHERE guild_id = %s AND game_id = %s AND is_rated = %s;
            """
            result = self._execute_query(query, (guild_id, game_id, is_rated), fetchone=True)
        else:
            query = """
                SELECT COUNT(*) as count FROM matches
                WHERE guild_id = %s AND game_id = %s;
            """
            result = self._execute_query(query, (guild_id, game_id), fetchone=True)

        return result['count'] if result else 0

    def count_users(self, guild_id: Optional[int] = None, is_active: bool = True) -> int:
        """Count users (optionally: distinct users who completed a match in the guild)."""
        if guild_id is not None:
            query = """
                SELECT COUNT(DISTINCT mp.user_id) as count
                FROM match_participants mp
                JOIN matches m ON mp.match_id = m.match_id
                WHERE m.guild_id = %s AND m.status = 'completed';
            """
            result = self._execute_query(query, (guild_id,), fetchone=True)
        else:
            query = """
                SELECT COUNT(*) as count FROM users
                WHERE is_active = %s;
            """
            result = self._execute_query(query, (is_active,), fetchone=True)

        return result['count'] if result else 0

    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        queries = {
            'total_users': "SELECT COUNT(*) FROM users WHERE is_active = TRUE",
            'total_guilds': "SELECT COUNT(*) FROM guilds WHERE is_active = TRUE",
            'total_games': "SELECT COUNT(*) FROM games WHERE is_active = TRUE",
            'total_matches': "SELECT COUNT(*) FROM matches",
            'active_matches': "SELECT COUNT(*) FROM matches WHERE status = 'in_progress'",
            'total_moves': "SELECT COUNT(*) FROM moves",
            'total_ratings': "SELECT COUNT(*) FROM user_game_ratings"
        }

        stats = {}
        for key, query in queries.items():
            result = self._execute_query(query, fetchone=True)
            stats[key] = result['count'] if result else 0

        return stats

    def health_check(self) -> bool:
        """Health check - verify database connection"""
        try:
            result = self._execute_query("SELECT 1 as check;", fetchone=True)
            return result is not None and result['check'] == 1
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    # ========================================================================
    # LEGACY COMPATIBILITY (for existing code)
    # ========================================================================

    def get_player(
        self,
        user: discord.User | discord.Member,
        guild_id: int
    ) -> Optional[InternalPlayer]:
        """
        Get an InternalPlayer object from the database (global per-game ratings).
        guild_id is ignored; kept for call-site compatibility.
        """
        user_id = user.id if isinstance(user, (discord.User, discord.Member, InternalPlayer)) else user
        preferences = self.get_user_preferences(user_id)
        metadata = preferences['preferences'] if preferences and preferences.get('preferences') else {}

        all_ratings = self.get_user_all_ratings(user_id)
        
        # Convert to old format {game_name: {mu, sigma}}
        ratings = {}
        for rating in all_ratings:
            game = self.get_game_by_id(rating.game_id)
            if game:
                ratings[game.game_name] = {'mu': rating.mu, 'sigma': rating.sigma}

        return InternalPlayer(
            ratings=ratings,
            user=user if isinstance(user, (discord.User, discord.Member)) else None,
            metadata=metadata,
            id=user_id
        )

    def record_analytics_event(
        self,
        event_type: str,
        user_id: Optional[int] = None,
        guild_id: Optional[int] = None,
        game_type: Optional[str] = None,
        match_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Record an analytics row (maps game_type slug to games.game_id; optional match_id).
        """
        game_id = None
        if game_type:
            game = self.get_game(game_type)
            if game:
                game_id = game.game_id

        self.record_event(event_type, user_id, guild_id, game_id, match_id, metadata)

    # ========================================================================
    # COMPATIBILITY METHODS (for old method names)
    # ========================================================================

    def get_game_leaderboard(
        self,
        member_user_ids: List[int],
        game_name: str,
        limit: int = 10,
        min_matches: int = 5
    ) -> List[Dict[str, Any]]:
        """Legacy method - maps to get_leaderboard(member_user_ids, ...)."""
        game = self.get_game(game_name)
        if not game:
            return []
        return self.get_leaderboard(
            member_user_ids, game.game_id, limit=limit, min_matches=min_matches
        )

    def get_user_game_ratings(
        self,
        user_id: int,
        game_name_or_id: int | str,
        guild_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Legacy method - get user rating (guild_id ignored)."""
        if isinstance(game_name_or_id, str):
            game = self.get_game(game_name_or_id)
            if not game:
                return None
            game_id = game.game_id
        else:
            game_id = game_name_or_id

        rating = self.get_user_rating(user_id, game_id)
        if not rating:
            return None

        # Return in old format
        return {
            'mu': rating.mu,
            'sigma': rating.sigma,
            'matches_played': rating.matches_played,
            'last_played': rating.last_played
        }

    def initialize_user_game_ratings(self, user_id: int, game_name: str, guild_id: Optional[int] = None):
        """Legacy method - initialize rating with game name instead of ID (guild_id ignored)."""
        game = self.get_game(game_name)
        if not game:
            raise ValueError(f"Game {game_name} not found")
        self.initialize_user_rating(user_id, game.game_id)

    def update_ratings_after_match(
        self,
        user_id: int,
        game_name: str,
        mu: float,
        sigma: float,
        matches_played_increment: int = 1,
        guild_id: Optional[int] = None,
    ):
        """Legacy method - update rating with game name instead of ID (guild_id ignored)."""
        game = self.get_game(game_name)
        if not game:
            raise ValueError(f"Game {game_name} not found")

        self.update_rating(
            user_id, game.game_id,
            mu, sigma, matches_increment=matches_played_increment
        )

    def reset_user_game_ratings(self, user_id: int, game_name: str, guild_id: Optional[int] = None):
        """Legacy method - reset rating with game name (guild_id ignored)."""
        game = self.get_game(game_name)
        if not game:
            raise ValueError(f"Game {game_name} not found")
        self.reset_user_rating(user_id, game.game_id)

    def delete_user_game_ratings(self, user_id: int, game_name: str, guild_id: Optional[int] = None):
        """Legacy method - delete rating with game name (guild_id ignored)."""
        game = self.get_game(game_name)
        if not game:
            raise ValueError(f"Game {game_name} not found")
        self.delete_user_rating(user_id, game.game_id)

    def count_matches_for_game(
        self,
        guild_id: int,
        game_name: str,
        is_rated: Optional[bool] = None
    ) -> int:
        """Legacy method - count matches with game name"""
        game = self.get_game(game_name)
        if not game:
            return 0
        return self.count_matches(guild_id, game.game_id, is_rated)

    def count_matches_for_user(
        self,
        user_id: int,
        guild_id: int,
        is_rated: Optional[bool] = None
    ) -> int:
        """Legacy method - count user matches"""
        query = """
            SELECT COUNT(DISTINCT m.match_id) AS total_matches
            FROM match_participants mp
            JOIN matches m ON mp.match_id = m.match_id
            WHERE mp.user_id = %s AND m.guild_id = %s
        """
        params = [user_id, guild_id]
        if is_rated is not None:
            query += " AND m.is_rated = %s"
            params.append(is_rated)
        query += ";"
        result = self._execute_query(query, tuple(params), fetchone=True)
        return result['total_matches'] if result else 0

    def get_match_details(self, match_id: int) -> Optional[Dict[str, Any]]:
        """Legacy method - get match details"""
        match = self.get_match(match_id)
        if not match:
            return None
        
        # Return dict format for compatibility
        return {
            'match_id': match.match_id,
            'match_code': match.match_code,
            'game_id': match.game_id,
            'guild_id': match.guild_id,
            'started': match.started_at,
            'ended': match.ended_at,
            'is_rated': match.is_rated,
            'game_data': match.game_config
        }

    def record_new_game(
        self,
        game_name: str,
        guild_id: int,
        started_at: datetime,
        is_rated: bool,
        game_data: Dict[str, Any]
    ) -> Tuple[int, str]:
        """Legacy method - record new game with game_name. Returns ``(match_id, match_code)``."""
        game = self.get_game(game_name)
        if not game:
            raise ValueError(f"Game {game_name} not found")

        self.create_guild(guild_id)
        status = game_data.get("status", MatchStatus.IN_PROGRESS.value)
        valid_statuses = {s.value for s in MatchStatus}
        if status not in valid_statuses:
            raise ValueError(f"Invalid match status: {status}")

        game_data_json = json.dumps(game_data or {})

        last_err: Optional[Exception] = None
        for _ in range(48):
            code = generate_match_code()
            try:
                with self.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO matches
                                (game_id, guild_id, channel_id, thread_id, started_at, status, is_rated,
                                 game_config, metadata, match_code)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                            RETURNING match_id;
                            """,
                            (
                                game.game_id,
                                guild_id,
                                0,
                                None,
                                started_at,
                                status,
                                is_rated,
                                game_data_json,
                                game_data_json,
                                code,
                            ),
                        )
                        result = cur.fetchone()
                    conn.commit()
                    return result["match_id"], code
            except pg_errors.UniqueViolation as e:
                last_err = e
                continue

        raise RuntimeError("Could not allocate a unique match_code") from last_err

    def create_game(
        self,
        game_name: str,
        guild_id: int,
        participants: List[int],
        is_rated: bool = True,
        channel_id: Optional[int] = None,
        thread_id: Optional[int] = None,
        game_config: Optional[Dict[str, Any]] = None
    ) -> Tuple[int, str]:
        """
        Legacy compatibility method - create game with game_name instead of game_id.
        Maps to new create_match method. Returns (match_id, match_code).
        """
        game = self.get_game(game_name)
        if not game:
            raise ValueError(f"Game {game_name} not found")
        
        resolved_channel_id = channel_id if channel_id is not None else 0

        return self.create_match(
            game_id=game.game_id,
            guild_id=guild_id,
            channel_id=resolved_channel_id,
            thread_id=thread_id,
            participants=participants,
            is_rated=is_rated,
            game_config=game_config or {},
        )

    def end_game(
        self,
        match_id: int,
        game_name: str,
        rating_updates: Dict[int, Dict[str, Any]],
        final_scores: Optional[Dict[int, float]]
    ):
        """
        Legacy compatibility method - end game with old format.
        Maps to new end_match method.
        """
        # Convert old format to new format
        # Old: rating_updates = {user_id: {uid, new_mu, new_sigma, mu_delta, sigma_delta, ranking}}
        # New: results = {user_id: {ranking, mu_delta, sigma_delta, new_mu, new_sigma, mu_before, sigma_before}}
        
        results = {}
        for user_id, data in rating_updates.items():
            results[user_id] = {
                'ranking': data.get('ranking', 1),
                'mu_delta': data['mu_delta'],
                'sigma_delta': data['sigma_delta'],
                'new_mu': data['new_mu'],
                'new_sigma': data['new_sigma'],
                'mu_before': data['new_mu'] - data['mu_delta'],
                'sigma_before': data['new_sigma'] - data['sigma_delta'],
                'score': final_scores.get(user_id) if final_scores else None,
                'is_draw': data.get('is_draw', False)
            }
        
        final_state = {
            'final_scores': final_scores,
            'rating_updates': rating_updates
        }
        
        # Call new end_match method
        self.end_match(match_id, final_state, results)

    def get_recent_matches_for_game(
        self,
        guild_id: int,
        game_name: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Legacy method - get recent matches with game name"""
        game = self.get_game(game_name)
        if not game:
            return []
        
        matches = self.get_recent_matches(guild_id, game.game_id, limit)
        return [
            {
                'match_id': m.match_id,
                'started': m.started_at,
                'ended': m.ended_at,
                'rated': m.is_rated
            }
            for m in matches
        ]

    def get_full_match_details(self, match_id: int) -> List[Dict[str, Any]]:
        """Legacy method - get full match with participants"""
        match = self.get_match(match_id)
        if not match:
            return []
        
        participants = self.get_participants(match_id)
        
        # Return in old format
        results = []
        for p in participants:
            rating = self.get_user_rating(p.user_id, match.game_id)
            results.append({
                'match_id': match_id,
                'game_id': match.game_id,
                'guild_id': match.guild_id,
                'started': match.started_at,
                'ended': match.ended_at,
                'rated': match.is_rated,
                'game_data': match.game_config,
                'user_id': p.user_id,
                'ranking': p.final_ranking,
                'mu_delta': p.mu_delta,
                'sigma_delta': p.sigma_delta,
                'mu': rating.mu if rating else None,
                'sigma': rating.sigma if rating else None
            })
        return results



# ============================================================================
# GLOBAL DATABASE INSTANCE
# ============================================================================

database: Optional[Database] = None


def startup():
    """Initialize global database instance"""
    global database
    config_db = constants.CONFIGURATION.get("db", {})
    try:
        db = Database(
            host=config_db.get("host", "localhost"),
            port=config_db.get("port", 5432),
            user=config_db.get("user", "playcord"),
            password=config_db.get("password", "password"),
            database=config_db.get("database", "playcord"),
            pool_size=config_db.get("pool_size", 10),
            max_overflow=config_db.get("max_overflow", 20),
            pool_timeout=config_db.get("pool_timeout", 30)
        )
        db_migrations.apply_migrations(db)
        db.refresh_sql_assets()
        db.sync_games_from_code()
        database = db
        logger.info("Database startup successful")
        return True
    except Exception as err:
        logger.error(f"Failed to connect to database: {err}")
        return False
