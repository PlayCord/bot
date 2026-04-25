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
        )
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
            return mention if mention else f"/{normalized}"

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
        self, key: str, default: str | None = None, *, locale: str | None = None
    ) -> str:
        selected_locale = locale or self.current_locale
        data = self._load_locale(selected_locale)
        value = _get_nested(data, key)
        if value is None:
            if default is not None:
                return self._replace_command_tokens(default)
            self.log.warning(
                "Missing locale key: %r in locale %r", key, selected_locale
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
