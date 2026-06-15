"""Dependency injection container for the refactored application."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from playcord.infrastructure.database import (
    AnalyticsRepository,
    GameRepository,
    GuildRepository,
    MaintenanceRepository,
    MatchRepository,
    MigrationRunner,
    PlayerRepository,
    PoolManager,
    ReplayRepository,
    RoleRepository,
)
from playcord.infrastructure.database.implementation.core.migrations import (
    apply_migrations,
)
from playcord.infrastructure.state.user_games import SessionRegistry

if TYPE_CHECKING:
    from playcord.infrastructure.config import Settings


@dataclass(slots=True)
class ApplicationContainer:
    """Owns shared infrastructure and application services."""

    settings: Settings
    pool_manager: PoolManager
    migration_runner: MigrationRunner
    registry: SessionRegistry = field(default_factory=SessionRegistry)
    players_repository: PlayerRepository = field(init=False, repr=False, compare=False)
    games_repository: GameRepository = field(init=False, repr=False, compare=False)
    maintenance_repository: MaintenanceRepository = field(
        init=False,
        repr=False,
        compare=False,
    )
    matches_repository: MatchRepository = field(init=False, repr=False, compare=False)
    replays_repository: ReplayRepository = field(init=False, repr=False, compare=False)
    guilds_repository: GuildRepository = field(init=False, repr=False, compare=False)
    roles_repository: RoleRepository = field(init=False, repr=False, compare=False)
    analytics_repository: AnalyticsRepository = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        database = self.pool_manager.connect()
        apply_migrations(database)

        self.games_repository = GameRepository(database)
        self.players_repository = PlayerRepository(
            database,
            self.games_repository,
        )
        self.analytics_repository = AnalyticsRepository(database, self.games_repository)
        self.maintenance_repository = MaintenanceRepository(
            database,
            self.games_repository,
        )
        self.guilds_repository = GuildRepository(
            database,
            self.analytics_repository,
            self.players_repository,
            self.games_repository,
            self.maintenance_repository,
        )
        self.matches_repository = MatchRepository(
            database,
            self.players_repository,
            self.guilds_repository,
            self.games_repository,
        )
        self.replays_repository = ReplayRepository(database)
        self.roles_repository = RoleRepository(database)

        self.migration_runner.run_startup(
            database,
            self.games_repository,
            self.analytics_repository,
            self.matches_repository,
        )

    def close(self) -> None:
        self.pool_manager.close()
