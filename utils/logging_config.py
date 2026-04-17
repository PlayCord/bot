import logging
import sys
from collections.abc import Mapping
from typing import Any

from utils.formatter import Formatter

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

    # Keep app logger inheriting from root unless a module explicitly overrides.
    logging.getLogger(root_name).setLevel(logging.NOTSET)

    # Do not align discord.py logger verbosity with bot-configured level.
    # Discord logger should always remain at INFO to avoid noisy debug logs.
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


def get_logger(name: str | None = None, *, root_name: str = DEFAULT_LOGGING_ROOT) -> logging.Logger:
    if name is None or not str(name).strip():
        return logging.getLogger(root_name)

    normalized = str(name).strip().strip(".")
    if normalized == root_name or normalized.startswith(f"{root_name}."):
        return logging.getLogger(normalized)
    return logging.getLogger(f"{root_name}.{normalized}")
