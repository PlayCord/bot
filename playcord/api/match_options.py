"""Lobby customization metadata before a game starts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from playcord.core.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class MatchOptionSpec:
    """One game option shown in the lobby UI."""

    key: str
    label: str
    kind: Literal["choices", "int", "bool", "preset"]
    default: str | int
    choices: tuple[tuple[str, str], ...] | None = None
    min_value: int | None = None
    max_value: int | None = None
    presets: tuple[tuple[str, dict[str, Any]], ...] | None = None

    def __post_init__(self) -> None:
        if self.kind == "choices":
            if not self.choices:
                msg = f"MatchOptionSpec {self.key!r}: choices required"
                raise ConfigurationError(
                    msg,
                )
            if self.default not in {value for _, value in self.choices}:
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
            preset_names = {name for name, _ in self.presets}
            if str(self.default) not in preset_names:
                msg = f"MatchOptionSpec {self.key!r}: default not in presets"
                raise ConfigurationError(
                    msg,
                )

    def allowed_values(self) -> set[str]:
        if self.kind == "choices":
            return {value for _, value in self.choices or ()}
        if self.kind == "bool":
            return {"true", "false"}
        if self.kind == "preset":
            return {name for name, _ in self.presets or ()}
        return {
            str(value)
            for value in range(
                int(self.min_value or 0),
                int(self.max_value or 0) + 1,
            )
        }

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
        for name, values in self.presets or ():
            if name == selected:
                return dict(values)
        return None
