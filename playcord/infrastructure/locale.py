"""Locale loading and translation helpers."""

from __future__ import annotations

import logging
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playcord.infrastructure.logging import get_logger

DEFAULT_LOCALE = "en"
COMMAND_TOKEN_RE = re.compile(r"\{command:([^{}]+)\}")


def _get_nested(data: dict[str, Any], key: str) -> Any | None:
    current: Any = data
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


@dataclass(slots=True)
class Translator:
    """A locale-aware string resolver."""

    locale_directory: Path = field(
        default_factory=lambda: (
            Path(__file__).resolve().parent.parent / "configuration" / "locale"
        ),
    )
    default_locale: str = DEFAULT_LOCALE
    current_locale: str = DEFAULT_LOCALE
    command_mentions: dict[str, str] = field(default_factory=dict)
    _cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    log: logging.Logger = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "log", get_logger("locale"))

    def _normalize_command_path(self, path: str) -> str:
        return " ".join(path.strip().lstrip("/").split()).lower()

    def _replace_command_tokens(self, text: str) -> str:
        if "{command:" not in text:
            return text

        def _resolve(match: re.Match[str]) -> str:
            raw_path = match.group(1)
            normalized = self._normalize_command_path(raw_path)
            mention = self.command_mentions.get(normalized)
            return mention or f"/{normalized}"

        return COMMAND_TOKEN_RE.sub(_resolve, text)

    def set_command_mentions(self, mentions: dict[str, str] | None) -> None:
        cleaned: dict[str, str] = {}
        for path, mention in (mentions or {}).items():
            normalized = self._normalize_command_path(path)
            mention_text = str(mention or "").strip()
            if normalized and mention_text:
                cleaned[normalized] = mention_text
        self.command_mentions = cleaned

    def _load_locale(self, locale_code: str) -> dict[str, Any]:
        if locale_code in self._cache:
            return self._cache[locale_code]

        locale_path = self.locale_directory / f"{locale_code}.toml"
        if not locale_path.exists():
            if locale_code != self.default_locale:
                self.log.warning(
                    "Locale %r not found, falling back to %r",
                    locale_code,
                    self.default_locale,
                )
                return self._load_locale(self.default_locale)
            raise FileNotFoundError(f"Default locale file not found: {locale_path}")

        with locale_path.open("rb") as handle:
            data = tomllib.load(handle)
        self._cache[locale_code] = data
        return data

    def get(
        self,
        key: str,
        default: str | None = None,
        *,
        locale: str | None = None,
    ) -> str:
        selected_locale = locale or self.current_locale
        data = self._load_locale(selected_locale)
        value = _get_nested(data, key)
        if value is None:
            if default is not None:
                return self._replace_command_tokens(default)
            self.log.warning(
                "Missing locale key: %r in locale %r",
                key,
                selected_locale,
            )
            return f"[{key}]"
        return self._replace_command_tokens(str(value))

    def fmt(
        self,
        key: str,
        default: str | None = None,
        *,
        locale: str | None = None,
        **kwargs: Any,
    ) -> str:
        template = self.get(key, default, locale=locale)
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError) as exc:
            self.log.warning("Failed to format locale key %r: %s", key, exc)
            return template

    def get_error(self, error_key: str, *, locale: str | None = None) -> str:
        return self.get(f"errors.{error_key}", f"[errors.{error_key}]", locale=locale)

    def get_dict(self, key: str, *, locale: str | None = None) -> dict[str, Any]:
        selected_locale = locale or self.current_locale
        data = self._load_locale(selected_locale)
        value = _get_nested(data, key)
        return value if isinstance(value, dict) else {}

    def has_key(self, key: str, *, locale: str | None = None) -> bool:
        selected_locale = locale or self.current_locale
        data = self._load_locale(selected_locale)
        return _get_nested(data, key) is not None

    def reload_locale(self, locale_code: str | None = None) -> None:
        if locale_code:
            self._cache.pop(locale_code, None)
        else:
            self._cache.clear()

    def plural(self, word: str, count: int) -> str:
        if count == 1:
            return self.get(f"plurals.{word}", word)
        return self.get(f"plurals.{word}s", f"{word}s")

    def brand(self, key: str, **kwargs: Any) -> str:
        if kwargs:
            return self.fmt(f"brand.{key}", **kwargs)
        return self.get(f"brand.{key}")

    def cmd_desc(self, command: str) -> str:
        return self.get(f"commands.{command}.description")

    def button(self, name: str) -> str:
        return self.get(f"buttons.{name}")


_standalone_translator: Translator | None = None


def _active_translator() -> Translator:
    from playcord.application.runtime_context import try_get_container

    container = try_get_container()
    if container is not None:
        return container.translator
    global _standalone_translator
    if _standalone_translator is None:
        _standalone_translator = Translator()
    return _standalone_translator


def get(key: str, default: str | None = None, *, locale: str | None = None) -> str:
    return _active_translator().get(key, default, locale=locale)


def fmt(
    key: str,
    default: str | None = None,
    *,
    locale: str | None = None,
    **kwargs: Any,
) -> str:
    return _active_translator().fmt(key, default, locale=locale, **kwargs)


def get_error(error_key: str, *, locale: str | None = None) -> str:
    return _active_translator().get(f"errors.{error_key}", None, locale=locale)


def get_dict(key: str, *, locale: str | None = None) -> dict[str, Any]:
    return _active_translator().get_dict(key, locale=locale)


def has_key(key: str, *, locale: str | None = None) -> bool:
    return _active_translator().has_key(key, locale=locale)


def set_locale(locale_code: str) -> None:
    t = _active_translator()
    t.current_locale = locale_code
    t._load_locale(locale_code)


def get_locale() -> str:
    return _active_translator().current_locale


def set_command_mentions(command_mentions: dict[str, str] | None) -> None:
    _active_translator().set_command_mentions(command_mentions)


def reload_locale(locale_code: str | None = None) -> None:
    _active_translator().reload_locale(locale_code)


def brand(key: str, **kwargs: Any) -> str:
    return _active_translator().brand(key, **kwargs)


def cmd_desc(command: str) -> str:
    return _active_translator().cmd_desc(command)


def button(name: str) -> str:
    return _active_translator().button(name)


def plural(word: str, count: int) -> str:
    return _active_translator().plural(word, count)
