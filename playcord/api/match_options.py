"""Lobby customization metadata before a game starts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from playcord.core.errors import ConfigurationError

ChoiceEntry = tuple[str, str] | tuple[str, str, str]
PresetEntry = tuple[str, dict[str, Any]] | tuple[str, dict[str, Any], str]


def _normalize_entry(
    entry: tuple[Any, ...],
    *,
    kind: Literal["choice", "preset"],
) -> tuple[Any, ...]:
    if len(entry) == 2:
        return entry[0], entry[1], None
    if len(entry) == 3:
        return entry[0], entry[1], entry[2]
    label = "choice" if kind == "choice" else "preset"
    msg = f"Invalid {label} entry {entry!r}; expected 2 or 3 elements"
    raise ConfigurationError(msg)


def _normalize_choice(entry: ChoiceEntry) -> tuple[str, str, str | None]:
    label, value, icon_key = _normalize_entry(entry, kind="choice")
    return str(label), str(value), icon_key


def _normalize_preset(entry: PresetEntry) -> tuple[str, dict[str, Any], str | None]:
    name, values, icon_key = _normalize_entry(entry, kind="preset")
    return str(name), dict(values), icon_key


@dataclass(frozen=True, slots=True)
class MatchOptionSpec:
    """One game option shown in the lobby settings UI."""

    key: str
    label: str
    kind: Literal["choices", "int", "bool", "preset"]
    default: str | int
    description: str | None = None
    choices: tuple[ChoiceEntry, ...] | None = None
    min_value: int | None = None
    max_value: int | None = None
    presets: tuple[PresetEntry, ...] | None = None

    def __post_init__(self) -> None:
        if self.kind == "choices":
            if not self.choices:
                msg = f"MatchOptionSpec {self.key!r}: choices required"
                raise ConfigurationError(
                    msg,
                )
            if self.default not in {value for _, value, *_ in map(_normalize_choice, self.choices)}:
                msg = f"MatchOptionSpec {self.key!r}: default not in choices"
                raise ConfigurationError(
                    msg,
                )
            return

        if self.kind == "int":
            if self.min_value is None or self.max_value is None:
                msg = f"MatchOptionSpec {self.key!r}: min_value and max_value required"
                raise ConfigurationError(
                    msg,
                )
            if self.min_value > self.max_value:
                msg = f"MatchOptionSpec {self.key!r}: min_value > max_value"
                raise ConfigurationError(
                    msg,
                )
            span = self.max_value - self.min_value + 1
            if span > 25:
                msg = f"MatchOptionSpec {self.key!r}: int range spans {span} options"
                raise ConfigurationError(
                    msg,
                )
            default = int(self.default)
            if default < self.min_value or default > self.max_value:
                msg = f"MatchOptionSpec {self.key!r}: default out of range"
                raise ConfigurationError(
                    msg,
                )
            return

        if self.kind == "bool":
            if str(self.default) not in {"true", "false"}:
                msg = (
                    f"MatchOptionSpec {self.key!r}: "
                    "bool default must be 'true' or 'false'"
                )
                raise ConfigurationError(
                    msg,
                )
            return

        if self.kind == "preset":
            if not self.presets:
                msg = f"MatchOptionSpec {self.key!r}: presets required"
                raise ConfigurationError(
                    msg,
                )
            preset_names = {name for name, _, *_ in map(_normalize_preset, self.presets)}
            if str(self.default) not in preset_names:
                msg = f"MatchOptionSpec {self.key!r}: default not in presets"
                raise ConfigurationError(
                    msg,
                )

    def allowed_values(self) -> set[str]:
        if self.kind == "choices":
            return {value for _, value, *_ in map(_normalize_choice, self.choices or ())}
        if self.kind == "bool":
            return {"true", "false"}
        if self.kind == "preset":
            return {name for name, _, *_ in map(_normalize_preset, self.presets or ())}
        return {
            str(value)
            for value in range(
                int(self.min_value or 0),
                int(self.max_value or 0) + 1,
            )
        }

    def select_options(self) -> list[tuple[str, str, bool, str | None]]:
        """Return ``(label, value, is_default, icon_key)`` tuples for lobby selects."""
        if self.kind == "choices":
            return [
                (label, value, str(value) == str(self.default), icon_key)
                for label, value, icon_key in map(_normalize_choice, self.choices or ())
            ]
        if self.kind == "int":
            return [
                (str(value), str(value), int(self.default) == value, None)
                for value in range(
                    int(self.min_value or 0),
                    int(self.max_value or 0) + 1,
                )
            ]
        if self.kind == "bool":
            return [
                ("Yes", "true", str(self.default) == "true", None),
                ("No", "false", str(self.default) == "false", None),
            ]
        if self.kind == "preset":
            return [
                (name, name, name == str(self.default), icon_key)
                for name, _, icon_key in map(_normalize_preset, self.presets or ())
            ]
        return []

    def coerce(self, raw: str) -> str | int:
        if self.kind in {"choices", "bool", "preset"}:
            return raw if raw in self.allowed_values() else str(self.default)

        try:
            value = int(raw)
        except ValueError:
            return int(self.default)
        if (self.min_value or 0) <= value <= (self.max_value or 0):
            return value
        return int(self.default)

    def applied_preset(self, raw: str) -> dict[str, Any] | None:
        if self.kind != "preset":
            return None
        selected = str(self.coerce(raw))
        for name, values, _icon in map(_normalize_preset, self.presets or ()):
            if name == selected:
                return dict(values)
        return None
