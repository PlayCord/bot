"""CLI entrypoint."""

from __future__ import annotations

import argparse
import sys

from playcord.cli.analytics import run as run_analytics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="playcord-cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    analytics = subparsers.add_parser("analytics", help="Render analytics summary")
    analytics.add_argument("--hours", type=int, default=24)

    args, remaining = parser.parse_known_args(argv)
    if args.command == "analytics":
        return run_analytics(["--hours", str(args.hours), *remaining])
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
