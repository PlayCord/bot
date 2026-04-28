"""Domain models and pure business rules."""

from playcord.domain.bot import BotDefinition
from playcord.domain.errors import (
    ConfigurationError,
    DomainError,
    IllegalMove,
    NotPlayersTurn,
    RuleViolation,
    ValidationError,
)
from playcord.domain.game import (
    Game,
    GameMetadata,
    Move,
    MoveParameter,
    ParameterKind,
    PlayerOrder,
    RoleMode,
    ensure_valid_player_count,
)
from playcord.domain.handlers import HandlerRef, HandlerSpec, handler
from playcord.domain.match import MatchOutcome, MatchOutcomeKind, Seat
from playcord.domain.match_options import MatchOptionSpec
from playcord.domain.player import Player
from playcord.domain.rating import Rating
from playcord.domain.replay import ReplayEvent, ReplayRecorder

__all__ = [
    "BotDefinition",
    "ConfigurationError",
    "DomainError",
    "Game",
    "GameMetadata",
    "HandlerRef",
    "HandlerSpec",
    "IllegalMove",
    "MatchOptionSpec",
    "MatchOutcome",
    "MatchOutcomeKind",
    "Move",
    "MoveParameter",
    "NotPlayersTurn",
    "ParameterKind",
    "Player",
    "PlayerOrder",
    "Rating",
    "ReplayEvent",
    "ReplayRecorder",
    "RoleMode",
    "RuleViolation",
    "Seat",
    "ValidationError",
    "handler",
    "ensure_valid_player_count",
]
