"""Lobby customization metadata before a game starts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from playcord.domain.errors import ConfigurationError


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
                raise ConfigurationError(
                    f"MatchOptionSpec {self.key!r}: choices required"
                )
            if self.default not in {value for _, value in self.choices}:
                raise ConfigurationError(
                    f"MatchOptionSpec {self.key!r}: default not in choices"
                )
            return

        if self.kind == "int":
            if self.min_value is None or self.max_value is None:
                raise ConfigurationError(
                    f"MatchOptionSpec {self.key!r}: min_value and max_value required"
                )
            if self.min_value > self.max_value:
                raise ConfigurationError(
                    f"MatchOptionSpec {self.key!r}: min_value > max_value"
                )
            span = self.max_value - self.min_value + 1
            if span > 25:
                raise ConfigurationError(
                    f"MatchOptionSpec {self.key!r}: int range spans {span} options"
                )
            default = int(self.default)
            if default < self.min_value or default > self.max_value:
                raise ConfigurationError(
                    f"MatchOptionSpec {self.key!r}: default out of range"
                )
            return

        if self.kind == "bool":
            if str(self.default) not in {"true", "false"}:
                raise ConfigurationError(
                    f"MatchOptionSpec {self.key!r}: bool default must be 'true' or 'false'"
                )
            return

        if self.kind == "preset":
            if not self.presets:
                raise ConfigurationError(
                    f"MatchOptionSpec {self.key!r}: presets required"
                )
            preset_names = {name for name, _ in self.presets}
            if str(self.default) not in preset_names:
                raise ConfigurationError(
                    f"MatchOptionSpec {self.key!r}: default not in presets"
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
