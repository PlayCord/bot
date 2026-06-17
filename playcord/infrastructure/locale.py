"""String loading helpers backed by ``configuration/locale/en.toml``."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from playcord.infrastructure.logging import get_logger

DEFAULT_LOCALE = "en"
COMMAND_TOKEN_RE = re.compile(r"\{command:([^{}]+)\}")

# Path to the single strings file (en.toml)
_STRINGS_PATH = (
    Path(__file__).resolve().parent.parent
    / "configuration"
    / "locale"
    / f"{DEFAULT_LOCALE}.toml"
)

_log = get_logger("locale")


def _load_strings() -> dict[str, Any]:
    if not _STRINGS_PATH.exists():
        raise FileNotFoundError(f"Strings file not found: {_STRINGS_PATH}")
    with _STRINGS_PATH.open("rb") as handle:
        return tomllib.load(handle)


_STRINGS: dict[str, Any] = _load_strings()
_COMMAND_MENTIONS: dict[str, str] = {}


def _get_nested(data: dict[str, Any], key: str) -> Any | None:
    current: Any = data
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _normalize_command_path(path: str) -> str:
    return " ".join(path.strip().lstrip("/").split()).lower()


def _replace_command_tokens(text: str) -> str:
    if "{command:" not in text:
        return text

    def _resolve(match: re.Match[str]) -> str:
        raw_path = match.group(1)
        normalized = _normalize_command_path(raw_path)
        mention = _COMMAND_MENTIONS.get(normalized)
        return mention or f"/{normalized}"

    return COMMAND_TOKEN_RE.sub(_resolve, text)


def set_command_mentions(mentions: dict[str, str] | None) -> None:
    cleaned: dict[str, str] = {}
    for path, mention in (mentions or {}).items():
        normalized = _normalize_command_path(path)
        mention_text = str(mention or "").strip()
        if normalized and mention_text:
            cleaned[normalized] = mention_text
    global _COMMAND_MENTIONS
    _COMMAND_MENTIONS = cleaned


def get(key: str, default: str | None = None) -> str:
    value = _get_nested(_STRINGS, key)
    if value is None:
        if default is not None:
            return _replace_command_tokens(default)
        _log.warning("Missing string key: %r", key)
        return f"[{key}]"
    return _replace_command_tokens(str(value))


def fmt(key: str, default: str | None = None, **kwargs: Any) -> str:
    template = get(key, default)
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError) as exc:
        _log.warning("Failed to format string key %r: %s", key, exc)
        return template


def get_dict(key: str) -> dict[str, Any]:
    value = _get_nested(_STRINGS, key)
    return value if isinstance(value, dict) else {}


def has_key(key: str) -> bool:
    return _get_nested(_STRINGS, key) is not None


def reload_strings() -> None:
    global _STRINGS
    _STRINGS = _load_strings()


def plural(word: str, count: int) -> str:
    if count == 1:
        return get(f"plurals.{word}", word)
    return get(f"plurals.{word}s", f"{word}s")


def brand(key: str, **kwargs: Any) -> str:
    if kwargs:
        return fmt(f"brand.{key}", **kwargs)
    return get(f"brand.{key}")


def cmd_desc(command: str) -> str:
    return get(f"commands.{command}.description")


def button(name: str) -> str:
    return get(f"buttons.{name}")


__all__ = [
    "brand",
    "button",
    "cmd_desc",
    "fmt",
    "get",
    "get_dict",
    "has_key",
    "plural",
    "reload_strings",
    "set_command_mentions",
]
