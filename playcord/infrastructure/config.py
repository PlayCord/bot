"""Typed application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from playcord.core.errors import ConfigurationError

_PLAYCORD_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = _PLAYCORD_ROOT / "configuration" / "config.yaml"


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    level: str = "INFO"


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    type: str = "postgresql"
    host: str = "localhost"
    port: int = 5432
    user: str = "playcord"
    password: str = ""
    database: str = "playcord"
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30


@dataclass(frozen=True, slots=True)
class BotSettings:
    secret: str
    auto_sync_commands: bool = False
    compare_command_tree_on_startup: bool = False
    owner_user_ids: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class RatingFloorsSettings:
    min_mu: float = 0.0
    min_sigma: float = 0.001


@dataclass(frozen=True, slots=True)
class Settings:
    bot: BotSettings
    db: DatabaseSettings
    logging: LoggingSettings
    analytics_retention_days: int = 30
    locale: str = "en"
    config_path: Path = DEFAULT_CONFIG_PATH
    ratings: RatingFloorsSettings = field(default_factory=RatingFloorsSettings)


def _as_int(value: str | None, *, env_key: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        msg = f"Environment variable {env_key} must be an integer"
        raise ConfigurationError(
            msg,
        ) from exc


def _apply_environment_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    updated = dict(raw)
    db = dict(updated.get("db") or {})

    direct = {
        "PLAYCORD_DB_TYPE": "type",
        "PLAYCORD_DB_HOST": "host",
        "PLAYCORD_DB_USER": "user",
        "PLAYCORD_DB_PASSWORD": "password",
        "PLAYCORD_DB_NAME": "database",
    }
    for env_key, field_name in direct.items():
        value = os.getenv(env_key)
        if value:
            db[field_name] = value

    numeric = {
        "PLAYCORD_DB_PORT": "port",
        "PLAYCORD_DB_POOL_SIZE": "pool_size",
        "PLAYCORD_DB_MAX_OVERFLOW": "max_overflow",
        "PLAYCORD_DB_POOL_TIMEOUT": "pool_timeout",
    }
    for env_key, field_name in numeric.items():
        value = _as_int(os.getenv(env_key), env_key=env_key)
        if value is not None:
            db[field_name] = value

    updated["db"] = db

    owner_env = os.getenv("PLAYCORD_OWNER_IDS", "").strip()
    if owner_env:
        bot = dict(updated.get("bot") or {})
        existing = {int(x) for x in (bot.get("owner_user_ids") or []) if x is not None}
        for part in owner_env.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                existing.add(int(part))
            except ValueError:
                continue
        bot["owner_user_ids"] = sorted(existing)
        updated["bot"] = bot

    return updated


def load_settings(path: str | Path = DEFAULT_CONFIG_PATH) -> Settings:
    config_path = Path(path)
    if not config_path.exists():
        msg = f"Configuration file not found: {config_path}"
        raise ConfigurationError(msg)

    with config_path.open("r", encoding="utf-8") as handle:
        raw = YAML().load(handle) or {}
    raw = _apply_environment_overrides(dict(raw))

    bot_raw = dict(raw.get("bot") or {})
    db_raw = dict(raw.get("db") or {})
    logging_raw = dict(raw.get("logging") or {})

    secret = str(bot_raw.get("secret") or raw.get("secret") or "").strip()
    if not secret:
        msg = "Bot secret is required in configuration"
        raise ConfigurationError(msg)

    ratings_raw = dict(raw.get("ratings") or {})

    owner_raw = bot_raw.get("owner_user_ids")
    if owner_raw is None:
        owner_user_ids: tuple[int, ...] = ()
    else:
        if not isinstance(owner_raw, (list, tuple)):
            msg = "bot.owner_user_ids must be a list of integers"
            raise ConfigurationError(
                msg,
            )
        owner_user_ids = tuple(int(x) for x in owner_raw)

    return Settings(
        bot=BotSettings(
            secret=secret,
            auto_sync_commands=bool(bot_raw.get("auto_sync_commands", False)),
            compare_command_tree_on_startup=bool(
                bot_raw.get("compare_command_tree_on_startup", False),
            ),
            owner_user_ids=owner_user_ids,
        ),
        db=DatabaseSettings(
            type=str(db_raw.get("type", "postgresql")),
            host=str(db_raw.get("host", "localhost")),
            port=int(db_raw.get("port", 5432)),
            user=str(db_raw.get("user", "playcord")),
            password=str(db_raw.get("password", "")),
            database=str(db_raw.get("database", "playcord")),
            pool_size=int(db_raw.get("pool_size", 10)),
            max_overflow=int(db_raw.get("max_overflow", 20)),
            pool_timeout=int(db_raw.get("pool_timeout", 30)),
        ),
        logging=LoggingSettings(level=str(logging_raw.get("level", "INFO"))),
        analytics_retention_days=int(raw.get("analytics_retention_days", 30)),
        locale=str(raw.get("locale", "en")),
        config_path=config_path,
        ratings=RatingFloorsSettings(
            min_mu=float(ratings_raw.get("min_mu", 0.0)),
            min_sigma=float(ratings_raw.get("min_sigma", 0.001)),
        ),
    )


_bound: Settings | None = None


def bind_settings(settings: Settings) -> None:
    """Bind loaded settings for code paths that cannot receive DI."""
    global _bound
    _bound = settings


def get_settings() -> Settings:
    if _bound is None:
        msg = "Application settings are not bound; call bind_settings() from bootstrap"
        raise ConfigurationError(
            msg,
        )
    return _bound


def reset_settings_binding() -> None:
    """Test helper."""
    global _bound
    _bound = None
