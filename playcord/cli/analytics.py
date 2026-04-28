"""Analytics CLI command."""

from __future__ import annotations

import argparse
import sys

from playcord.application.container import ApplicationContainer
from playcord.infrastructure import Translator, load_settings
from playcord.infrastructure.db import MigrationRunner, PoolManager
from playcord.infrastructure.logging import configure_logging, get_logger
from playcord.utils.analytics import render_analytics_markdown_summary

log = get_logger("cli.analytics")


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render PlayCord analytics summary.")
    parser.add_argument("--hours", type=int, default=24)
    args = parser.parse_args(argv)

    configure_logging("INFO")
    try:
        settings = load_settings()
        container = ApplicationContainer(
            settings=settings,
            translator=Translator(current_locale=settings.locale),
            pool_manager=PoolManager(settings.db),
            migration_runner=MigrationRunner(
                analytics_retention_days=settings.analytics_retention_days
            ),
        )
    except Exception:
        log.exception("Database startup failed.")
        return 1

    try:
        hours = max(1, min(720, args.hours))
        repo = container.analytics_repository
        counts = repo.get_summary(hours=hours)
        by_game = repo.get_event_counts_by_game(hours=hours)
        recent = repo.get_recent_events(hours=hours, limit=20)
        summary = render_analytics_markdown_summary(counts, by_game, recent, hours)
        for line in summary:
            sys.stdout.write(line + "\n")
        return 0
    finally:
        container.close()
