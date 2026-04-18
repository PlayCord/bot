"""Dependency injection container for the refactored application."""

from __future__ import annotations

from dataclasses import dataclass, field

from playcord.application.services.analytics import AnalyticsService
from playcord.application.services.game_session import GameSessionService
from playcord.application.services.matchmaking import MatchmakingService
from playcord.application.services.rating import RatingService
from playcord.application.services.replay import ReplayService
from playcord.application.services.session_registry import SessionRegistry
from playcord.application.services.stats import StatsService
from playcord.infrastructure.config import Settings
from playcord.infrastructure.db import (
    AnalyticsRepository,
    GameRepository,
    MatchRepository,
    MigrationRunner,
    PlayerRepository,
    PoolManager,
    ReplayRepository,
)
from playcord.infrastructure.locale import Translator


@dataclass(slots=True)
class ApplicationContainer:
    """Owns shared infrastructure and application services."""

    settings: Settings
    translator: Translator
    pool_manager: PoolManager
    migration_runner: MigrationRunner
    registry: SessionRegistry = field(default_factory=SessionRegistry)
    players: PlayerRepository = field(init=False, repr=False, compare=False)
    games: GameRepository = field(init=False, repr=False, compare=False)
    matches: MatchRepository = field(init=False, repr=False, compare=False)
    replays: ReplayRepository = field(init=False, repr=False, compare=False)
    analytics_repository: AnalyticsRepository = field(
        init=False, repr=False, compare=False
    )
    analytics: AnalyticsService = field(init=False, repr=False, compare=False)
    replay_service: ReplayService = field(init=False, repr=False, compare=False)
    rating_service: RatingService = field(init=False, repr=False, compare=False)
    stats_service: StatsService = field(init=False, repr=False, compare=False)
    matchmaking_service: MatchmakingService = field(
        init=False, repr=False, compare=False
    )
    game_session_service: GameSessionService = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        database = self.pool_manager.connect()
        self.migration_runner.apply(database)

        self.players = PlayerRepository(database)
        self.games = GameRepository(database)
        self.matches = MatchRepository(database)
        self.replays = ReplayRepository(database)
        self.analytics_repository = AnalyticsRepository(database)

        self.analytics = AnalyticsService(self.analytics_repository)
        self.replay_service = ReplayService(self.replays)
        self.rating_service = RatingService(self.players)
        self.stats_service = StatsService(self.matches, self.players)
        self.matchmaking_service = MatchmakingService(self.registry)
        self.game_session_service = GameSessionService(
            registry=self.registry,
            matches=self.matches,
            replays=self.replays,
            ratings=self.players,
        )

    def close(self) -> None:
        self.pool_manager.close()
