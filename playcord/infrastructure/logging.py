"""Logging configuration for PlayCord."""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping
from logging import Logger
from typing import Any


class Formatter(logging.Formatter):
    """Colored console formatter for local bot logs."""

    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = (
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
    )

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


DEFAULT_LOGGING_ROOT = "playcord"
DEFAULT_LEVEL = logging.INFO


def parse_log_level(level: str | int | None, default: int = DEFAULT_LEVEL) -> int:
    if isinstance(level, int):
        return level

    text = str(level or "").strip()
    if not text:
        return default

    if text.isdigit():
        try:
            return int(text)
        except ValueError:
            return default

    resolved = getattr(logging, text.upper(), None)
    return resolved if isinstance(resolved, int) else default


def configure_logging(
    level: str | int | None = DEFAULT_LEVEL,
    *,
    root_name: str = DEFAULT_LOGGING_ROOT,
) -> int:
    resolved_level = parse_log_level(level)

    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setLevel(resolved_level)
    stream_handler.setFormatter(Formatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)
    root_logger.handlers = [stream_handler]

    logging.getLogger(root_name).setLevel(logging.NOTSET)
    logging.getLogger("discord").setLevel(logging.INFO)
    return resolved_level


def configure_logging_from_config(
    config: Mapping[str, Any] | None,
    *,
    default_level: int = DEFAULT_LEVEL,
    root_name: str = DEFAULT_LOGGING_ROOT,
) -> int:
    level_name = ((config or {}).get("logging", {}) or {}).get("level", default_level)
    return configure_logging(level_name, root_name=root_name)


def get_logger(
    name: str | None = None,
    *,
    root_name: str = DEFAULT_LOGGING_ROOT,
) -> logging.Logger:
    if name is None or not str(name).strip():
        return logging.getLogger(root_name)

    normalized = str(name).strip().strip(".")
    if normalized == root_name or normalized.startswith(f"{root_name}."):
        return logging.getLogger(normalized)
    return logging.getLogger(f"{root_name}.{normalized}")


__all__ = [
    "DEFAULT_LEVEL",
    "DEFAULT_LOGGING_ROOT",
    "Logger",
    "configure_logging",
    "configure_logging_from_config",
    "get_logger",
    "parse_log_level",
]
