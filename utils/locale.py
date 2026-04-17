"""
Locale/Localization utilities for PlayCord.

This module provides a simple way to access localized strings from TOML files.
All user-facing strings should be retrieved through this module to enable
future localization support.

Usage:
    from utils.locale import get, fmt

    # Simple string retrieval
    title = get("help.main.title")  # Returns the string

    # String with variable formatting
    welcome = fmt("welcome.title", name="PlayCord")  # Returns formatted string

    # Get error messages
    error = get_error("not_in_matchmaking")  # Returns (description, suggestion)
"""

import re
import tomllib
from pathlib import Path
from typing import Any

from utils.logging_config import get_logger

# Default locale
DEFAULT_LOCALE = "en"

# Cache for loaded locale data
_locale_cache: dict[str, dict] = {}

# Current active locale
_current_locale = DEFAULT_LOCALE

# Slash command mention token support (`{command:play}` / `{command:playcord help}`)
_COMMAND_TOKEN_RE = re.compile(r"\{command:([^{}]+)\}")
_command_mentions: dict[str, str] = {}
log = get_logger("locale")


def _load_locale(locale_code: str) -> dict:
    """Load a locale file and cache it."""
    if locale_code in _locale_cache:
        return _locale_cache[locale_code]

    locale_path = (
        Path(__file__).parent.parent
        / "configuration"
        / "locale"
        / f"{locale_code}.toml"
    )

    if not locale_path.exists():
        if locale_code != DEFAULT_LOCALE:
            # Fall back to default locale
            log.warning(
                "Locale %r not found, falling back to %r", locale_code, DEFAULT_LOCALE
            )
            return _load_locale(DEFAULT_LOCALE)
        else:
            raise FileNotFoundError(f"Default locale file not found: {locale_path}")

    with open(locale_path, "rb") as f:
        data = tomllib.load(f)

    _locale_cache[locale_code] = data
    return data


def set_locale(locale_code: str) -> None:
    """Set the current active locale."""
    global _current_locale
    _current_locale = locale_code
    # Pre-load the locale to verify it exists
    _load_locale(locale_code)


def get_locale() -> str:
    """Get the current active locale code."""
    return _current_locale


def _get_nested(data: dict, key: str, default: Any = None) -> Any:
    """
    Get a value from a nested dictionary using dot notation.

    Example: _get_nested(data, "help.main.title")
             returns data["help"]["main"]["title"]
    """
    keys = key.split(".")
    current = data

    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return default

    return current


def _normalize_command_path(path: str) -> str:
    """Normalize slash command path text to a canonical lookup key."""
    return " ".join(path.strip().lstrip("/").split()).lower()


def _replace_command_tokens(text: str) -> str:
    """Replace `{command:...}` locale tokens with command mentions or plain `/path` fallback."""
    if "{command:" not in text:
        return text

    def _resolve(match: re.Match[str]) -> str:
        raw_path = match.group(1)
        normalized = _normalize_command_path(raw_path)
        if not normalized:
            return match.group(0)
        mention = _command_mentions.get(normalized)
        return mention if mention else f"/{normalized}"

    return _COMMAND_TOKEN_RE.sub(_resolve, text)


def set_command_mentions(command_mentions: dict[str, str] | None) -> None:
    """Register slash command mention strings used by `{command:...}` locale tokens."""
    global _command_mentions
    cleaned: dict[str, str] = {}
    for path, mention in (command_mentions or {}).items():
        normalized = _normalize_command_path(str(path))
        mention_text = str(mention or "").strip()
        if normalized and mention_text:
            cleaned[normalized] = mention_text
    _command_mentions = cleaned


def get(key: str, default: str = None, locale: str = None) -> str:
    """
    Get a localized string by its key.

    Args:
        key: Dot-notation path to the string (e.g., "help.main.title")
        default: Default value if key is not found (defaults to key itself)
        locale: Optional locale override (uses current locale if not specified)

    Returns:
        The localized string, or the default/key if not found
    """
    locale = locale or _current_locale
    data = _load_locale(locale)

    result = _get_nested(data, key)

    if result is None:
        if default is not None:
            return _replace_command_tokens(str(default))
        log.warning("Missing locale key: %r in locale %r", key, locale)
        return (
            f"[{key}]"  # Return key wrapped in brackets to make missing strings visible
        )

    return _replace_command_tokens(str(result))


def fmt(key: str, default: str = None, locale: str = None, **kwargs) -> str:
    """
    Get a localized string and format it with the provided variables.

    Uses Python's str.format() for variable substitution.
    Variables in the string should be marked with {variable_name}.

    Args:
        key: Dot-notation path to the string
        default: Default value if key is not found
        locale: Optional locale override
        **kwargs: Variables to substitute in the string

    Returns:
        The formatted localized string

    Example:
        fmt("welcome.title", name="PlayCord")
        # If welcome.title = "👋 Welcome to {name}!"
        # Returns: "👋 Welcome to PlayCord!"
    """
    template = get(key, default, locale)

    try:
        return template.format(**kwargs)
    except KeyError as e:
        log.warning("Missing format variable %s for key %r", e, key)
        return template
    except ValueError as e:
        log.warning("Invalid format string %r for key %r: %s", template, key, e)
        return template


def get_error(error_key: str, locale: str = None) -> str:
    """
    Get a localized error message by its key.

    Errors are stored as a single message under the `[errors]` table
    (e.g. `errors.not_in_matchmaking = "..."`). This function returns
    that single message string. Backward-compatibility for the old
    nested `errors.<key>.description` / `.suggestion` format has been
    removed.

    Args:
        error_key: The error identifier (e.g., "not_in_matchmaking")
        locale: Optional locale override

    Returns:
        The localized error message string, or a generic fallback.
    """
    locale = locale or _current_locale

    # Return the consolidated single-message entry or None
    return get(f"errors.{error_key}", None, locale)


def get_dict(key: str, locale: str = None) -> dict:
    """
    Get a dictionary of strings from a locale section.

    Useful for getting all values in a section, like textify variations.

    Args:
        key: Dot-notation path to the section (e.g., "buttons.textify.join")
        locale: Optional locale override

    Returns:
        The dictionary at that key, or empty dict if not found
    """
    locale = locale or _current_locale
    data = _load_locale(locale)

    result = _get_nested(data, key)

    if isinstance(result, dict):
        return result
    return {}


def has_key(key: str, locale: str = None) -> bool:
    """
    Check if a locale key exists.

    Args:
        key: Dot-notation path to check
        locale: Optional locale override

    Returns:
        True if the key exists, False otherwise
    """
    locale = locale or _current_locale
    data = _load_locale(locale)
    return _get_nested(data, key) is not None


def reload_locale(locale_code: str = None) -> None:
    """
    Clear the cache and reload a locale file.

    Args:
        locale_code: Specific locale to reload, or None to clear all
    """
    global _locale_cache

    if locale_code:
        if locale_code in _locale_cache:
            del _locale_cache[locale_code]
    else:
        _locale_cache = {}


# Convenience functions for common patterns
def brand(key: str, **kwargs) -> str:
    """Shorthand for brand-related strings."""
    return fmt(f"brand.{key}", **kwargs) if kwargs else get(f"brand.{key}")


def cmd_desc(command: str) -> str:
    """Get a command description."""
    return get(f"commands.{command}.description")


def button(name: str) -> str:
    """Get a button label."""
    return get(f"buttons.{name}")


def plural(word: str, count: int) -> str:
    """
    Get the correct singular/plural form.

    Args:
        word: Base word (e.g., "game", "player")
        count: The count to determine plurality

    Returns:
        The singular or plural form
    """
    if count == 1:
        return get(f"plurals.{word}", word)
    return get(f"plurals.{word}s", f"{word}s")


# Pre-load the default locale on module import
try:
    _load_locale(DEFAULT_LOCALE)
except FileNotFoundError:
    log.error("Could not load default locale %r", DEFAULT_LOCALE)
