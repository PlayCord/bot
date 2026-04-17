import argparse
import sys

from ruamel.yaml import YAML

import configuration.constants as constants
from utils import database as db
from utils.analytics import render_analytics_markdown_summary


def load_configuration() -> dict:
    with open(constants.CONFIG_FILE) as config_file:
        return YAML().load(config_file) or {}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print PlayCord analytics summaries from the database."
    )
    parser.add_argument(
        "--hours", type=int, default=24, help="Lookback window in hours (default: 24)."
    )
    args = parser.parse_args()

    constants.CONFIGURATION = load_configuration()
    if not db.startup():
        print("Database startup failed.", file=sys.stderr)
        return 1

    hours = max(1, min(args.hours, 24 * 30))
    counts = db.database.get_analytics_event_counts(hours=hours)
    by_game = db.database.get_analytics_event_counts_by_game(hours=hours)
    recent = db.database.get_analytics_recent_events(hours=hours, limit=20)

    for line in render_analytics_markdown_summary(counts, by_game, recent, hours):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
