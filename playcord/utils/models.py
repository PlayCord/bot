"""
PlayCord Data Models
Data classes representing database entities for type safety and easier data handling.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# ============================================================================
# ENUMS
# ============================================================================


class MatchStatus(str, Enum):
    """Status of a match"""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    ABANDONED = "abandoned"


class EventType(str, Enum):
    """Analytics event types (single source of truth; used by utils.analytics.register_event)."""

    GAME_STARTED = "game_started"
    GAME_COMPLETED = "game_completed"
    GAME_ABANDONED = "game_abandoned"
    MATCHMAKING_JOINED = "matchmaking_joined"
    MATCHMAKING_LEFT = "matchmaking_left"
    MATCHMAKING_MATCHED = "matchmaking_matched"
    MATCHMAKING_STARTED = "matchmaking_started"
    MATCHMAKING_COMPLETED = "matchmaking_completed"
    MATCHMAKING_CANCELLED = "matchmaking_cancelled"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    MOVE_MADE = "move_made"
    MOVE_VALID = "move_valid"
    MOVE_INVALID = "move_invalid"
    MOVE_REJECTED = "move_rejected"
    COMMAND_USED = "command_used"
    ERROR_OCCURRED = "error_occurred"
    BOT_STARTED = "bot_started"
    GUILD_JOINED = "guild_joined"
    GUILD_LEFT = "guild_left"
    RATING_UPDATED = "rating_updated"
    SKILL_DECAY_APPLIED = "skill_decay_applied"


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class Guild:
    """Represents a Discord guild/server"""

    guild_id: int
    joined_at: datetime
    settings: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a guild setting with optional default"""
        return self.settings.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        """Set a guild setting"""
        self.settings[key] = value


@dataclass
class User:
    """Represents a Discord user"""

    user_id: int
    username: str
    joined_at: datetime
    preferences: dict[str, Any] = field(default_factory=dict)
    is_bot: bool = False
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference with optional default"""
        return self.preferences.get(key, default)

    def set_preference(self, key: str, value: Any) -> None:
        """Set a user preference"""
        self.preferences[key] = value

    @property
    def mention(self) -> str:
        """Discord mention string"""
        return f"<@{self.user_id}>"


@dataclass
class Game:
    """Represents a game type"""

    game_id: int
    game_name: str
    display_name: str
    min_players: int
    max_players: int
    rating_config: dict[str, float]
    game_metadata: dict[str, Any] = field(default_factory=dict)
    game_schema_version: int = 1
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def get_trueskill_param(self, param: str) -> float:
        """Get a TrueSkill parameter"""
        return self.rating_config.get(param, 0.0)

    @property
    def sigma(self) -> float:
        return self.get_trueskill_param("sigma")

    @property
    def beta(self) -> float:
        return self.get_trueskill_param("beta")

    @property
    def tau(self) -> float:
        return self.get_trueskill_param("tau")

    @property
    def draw_probability(self) -> float:
        return self.get_trueskill_param("draw")

    @property
    def default_mu(self) -> float:
        return self.get_trueskill_param("default_mu")

    @property
    def default_sigma(self) -> float:
        return self.get_trueskill_param("default_sigma")


@dataclass
class Rating:
    """Represents a user's global rating for a specific game (one row per user per game)."""

    rating_id: int
    user_id: int
    game_id: int
    mu: float
    sigma: float
    matches_played: int = 0
    last_played: datetime | None = None
    last_sigma_increase: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def conservative_rating(self) -> float:
        """Conservative rating estimate (mu - 3*sigma)"""
        return self.mu - (3.0 * self.sigma)

    def is_uncertain(self, threshold: float = 0.5) -> bool:
        """Check if rating is uncertain based on sigma threshold"""
        return self.sigma > (threshold * self.mu)

    def format_rating(self, uncertainty_threshold: float = 0.20) -> str:
        """Format rating with uncertainty indicator"""
        rating = self.conservative_rating
        if self.is_uncertain(uncertainty_threshold):
            return f"{round(rating)}?"
        return str(round(rating))


@dataclass
class Match:
    """Represents a game match"""

    match_id: int
    game_id: int
    guild_id: int
    channel_id: int
    thread_id: int | None
    started_at: datetime
    ended_at: datetime | None
    status: MatchStatus
    is_rated: bool = True
    game_config: dict[str, Any] = field(default_factory=dict)
    match_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def duration_seconds(self) -> int | None:
        """Match duration in seconds"""
        if self.ended_at is None:
            return None
        return int((self.ended_at - self.started_at).total_seconds())

    @property
    def is_finished(self) -> bool:
        """Check if match is finished"""
        return self.status in (
            MatchStatus.COMPLETED,
            MatchStatus.INTERRUPTED,
            MatchStatus.ABANDONED,
        )

    @property
    def is_in_progress(self) -> bool:
        """Check if match is currently in progress"""
        return self.status == MatchStatus.IN_PROGRESS


@dataclass
class Participant:
    """Represents a participant in a match"""

    participant_id: int
    match_id: int
    user_id: int
    player_number: int
    final_ranking: int | None = None
    score: float | None = None
    mu_before: float | None = None
    sigma_before: float | None = None
    mu_delta: float = 0.0
    sigma_delta: float = 0.0
    joined_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def mu_after(self) -> float | None:
        """Rating after the match"""
        if self.mu_before is None:
            return None
        return self.mu_before + self.mu_delta

    @property
    def sigma_after(self) -> float | None:
        """Uncertainty after the match"""
        if self.sigma_before is None:
            return None
        return self.sigma_before + self.sigma_delta

    @property
    def is_winner(self) -> bool:
        """Check if participant won"""
        return self.final_ranking == 1 if self.final_ranking is not None else False


@dataclass
class Move:
    """Represents a single move in a match"""

    move_id: int
    match_id: int
    user_id: int | None  # None for system moves
    move_number: int
    move_data: dict[str, Any]
    kind: str = "move"
    game_state_after: dict[str, Any] | None = None
    is_game_affecting: bool = True
    created_at: datetime | None = None
    time_taken_ms: int | None = None

    @property
    def is_system_move(self) -> bool:
        """Check if move was made by the system"""
        return self.user_id is None

    @property
    def time_taken_seconds(self) -> float | None:
        """Time taken in seconds"""
        if self.time_taken_ms is None:
            return None
        return self.time_taken_ms / 1000.0


@dataclass
class AnalyticsEvent:
    """Represents an analytics event"""

    event_id: int
    event_type: EventType
    created_at: datetime
    user_id: int | None = None
    guild_id: int | None = None
    game_id: int | None = None
    match_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RatingHistory:
    """Represents a historical rating change"""

    history_id: int
    user_id: int
    guild_id: int
    game_id: int
    match_id: int
    mu_before: float
    sigma_before: float
    mu_after: float
    sigma_after: float
    created_at: datetime

    @property
    def mu_delta(self) -> float:
        """Change in mu"""
        return self.mu_after - self.mu_before

    @property
    def sigma_delta(self) -> float:
        """Change in sigma"""
        return self.sigma_after - self.sigma_before

    @property
    def rating_change(self) -> float:
        """Change in conservative rating"""
        before = self.mu_before - (3.0 * self.sigma_before)
        after = self.mu_after - (3.0 * self.sigma_after)
        return after - before


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def row_to_user(row: dict[str, Any]) -> User:
    """Convert database row to User object"""
    return User(
        user_id=row["user_id"],
        username=row["username"],
        joined_at=row.get("joined_at") or row.get("created_at"),
        preferences=row.get("preferences", {}),
        is_bot=row.get("is_bot", False),
        is_active=row.get("is_active", True),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def row_to_guild(row: dict[str, Any]) -> Guild:
    """Convert database row to Guild object"""
    return Guild(
        guild_id=row["guild_id"],
        joined_at=row.get("joined_at") or row.get("created_at"),
        settings=row.get("settings", {}),
        is_active=row.get("is_active", True),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def row_to_game(row: dict[str, Any]) -> Game:
    """Convert database row to Game object"""
    return Game(
        game_id=row["game_id"],
        game_name=row["game_name"],
        display_name=row["display_name"],
        min_players=row["min_players"],
        max_players=row["max_players"],
        rating_config=row["rating_config"],
        game_metadata=row.get("game_metadata", {}),
        game_schema_version=row.get("game_schema_version", 1),
        is_active=row.get("is_active", True),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def row_to_rating(row: dict[str, Any]) -> Rating:
    """Convert database row to Rating object"""
    return Rating(
        rating_id=row["rating_id"],
        user_id=row["user_id"],
        game_id=row["game_id"],
        mu=row["mu"],
        sigma=row["sigma"],
        matches_played=row.get("matches_played", 0),
        last_played=row.get("last_played"),
        last_sigma_increase=row.get("last_sigma_increase"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def row_to_match(row: dict[str, Any]) -> Match:
    """Convert database row to Match object"""
    return Match(
        match_id=row["match_id"],
        game_id=row["game_id"],
        guild_id=row["guild_id"],
        channel_id=row["channel_id"],
        thread_id=row.get("thread_id"),
        started_at=row["started_at"],
        ended_at=row.get("ended_at"),
        status=MatchStatus(row["status"]),
        is_rated=row.get("is_rated", True),
        game_config=row.get("game_config", {}),
        match_code=row.get("match_code"),
        metadata=row.get("metadata", {}),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def row_to_participant(row: dict[str, Any]) -> Participant:
    """Convert database row to Participant object"""
    return Participant(
        participant_id=row["participant_id"],
        match_id=row["match_id"],
        user_id=row["user_id"],
        player_number=row["player_number"],
        final_ranking=row.get("final_ranking"),
        score=row.get("score"),
        mu_before=row.get("mu_before"),
        sigma_before=row.get("sigma_before"),
        mu_delta=row.get("mu_delta", 0.0),
        sigma_delta=row.get("sigma_delta", 0.0),
        joined_at=row.get("joined_at"),
        updated_at=row.get("updated_at"),
    )


def row_to_move(row: dict[str, Any]) -> Move:
    """Convert database row to Move object"""
    return Move(
        move_id=row["move_id"],
        match_id=row["match_id"],
        user_id=row.get("user_id"),
        move_number=row["move_number"],
        kind=row.get("kind", "move"),
        move_data=row["move_data"],
        game_state_after=row.get("game_state_after"),
        is_game_affecting=row.get("is_game_affecting", True),
        created_at=row.get("created_at"),
        time_taken_ms=row.get("time_taken_ms"),
    )
