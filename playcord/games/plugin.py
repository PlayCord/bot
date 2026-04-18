"""Game plugin protocol and legacy adapters."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Protocol

from playcord.domain import (
    BotDefinition,
    GameMetadata,
    MatchOptionSpec,
    Move,
    MoveParameter,
    ParameterKind,
)


def _parameter_kind_from_legacy(argument: Any) -> ParameterKind:
    type_name = getattr(argument, "type", "string")
    if type_name == "int":
        return ParameterKind.integer
    if getattr(argument, "options", None) is not None:
        return ParameterKind.dropdown
    return ParameterKind.string


def _convert_legacy_argument(argument: Any) -> MoveParameter:
    choices = None
    if getattr(argument, "options", None) is not None:
        choices = tuple((choice.name, str(choice.value)) for choice in argument.options)
    return MoveParameter(
        name=getattr(argument, "name"),
        description=getattr(argument, "description", ""),
        kind=_parameter_kind_from_legacy(argument),
        optional=bool(getattr(argument, "optional", False)),
        autocomplete=getattr(argument, "autocomplete", None),
        force_reload=bool(getattr(argument, "force_reload", False)),
        choices=choices,
        min_value=getattr(argument, "min_value", None),
        max_value=getattr(argument, "max_value", None),
    )


def _convert_legacy_move(move: Any) -> Move:
    options = tuple(_convert_legacy_argument(option) for option in (move.options or []))
    return Move(
        name=move.name,
        description=move.description or move.name,
        options=options,
        require_current_turn=bool(getattr(move, "require_current_turn", True)),
        callback=getattr(move, "callback", None),
        is_game_affecting=bool(getattr(move, "is_game_affecting", True)),
    )


def _convert_legacy_bots(raw: dict[str, Any]) -> dict[str, BotDefinition]:
    return {
        difficulty: BotDefinition(
            description=getattr(bot, "description", ""),
            callback=getattr(bot, "callback", None),
        )
        for difficulty, bot in raw.items()
    }


def _convert_legacy_match_options(raw: tuple[Any, ...]) -> tuple[MatchOptionSpec, ...]:
    options: list[MatchOptionSpec] = []
    for option in raw:
        options.append(
            MatchOptionSpec(
                key=option.key,
                label=option.label,
                kind=option.kind,
                default=option.default,
                choices=option.choices,
                min_value=option.min_value,
                max_value=option.max_value,
                presets=option.presets,
            )
        )
    return tuple(options)


class GamePlugin(Protocol):
    """Describes a game implementation exposed by the command tree."""

    key: str

    def load(self) -> type[Any]:
        """Return the underlying game class."""

    def metadata(self) -> GameMetadata:
        """Return typed metadata for the game."""


@dataclass(frozen=True, slots=True)
class LegacyGamePlugin:
    """Adapter around the existing `games/*.py` implementations."""

    key: str
    module_name: str
    class_name: str

    def load(self) -> type[Any]:
        module = importlib.import_module(self.module_name)
        return getattr(module, self.class_name)

    def metadata(self) -> GameMetadata:
        game_class = self.load()
        return GameMetadata(
            key=self.key,
            name=getattr(game_class, "name", self.key),
            summary=getattr(game_class, "summary", ""),
            description=getattr(game_class, "description", ""),
            move_group_description=getattr(
                game_class, "move_command_group_description", self.key
            ),
            player_count=getattr(game_class, "player_count", 2),
            author=getattr(game_class, "author", "Unknown"),
            version=getattr(game_class, "version", "1.0"),
            author_link=getattr(game_class, "author_link", ""),
            source_link=getattr(game_class, "source_link", ""),
            time=getattr(game_class, "time", ""),
            difficulty=getattr(game_class, "difficulty", ""),
            bots=_convert_legacy_bots(getattr(game_class, "bots", {})),
            moves=tuple(
                _convert_legacy_move(move) for move in getattr(game_class, "moves", [])
            ),
            player_order=getattr(game_class, "player_order", "random"),
            role_mode=getattr(game_class, "role_mode", "none"),
            player_roles=getattr(game_class, "player_roles", None),
            trueskill_parameters=dict(
                getattr(game_class, "trueskill_parameters", {}) or {}
            ),
            customizable_options=_convert_legacy_match_options(
                tuple(getattr(game_class, "customizable_options", ()) or ())
            ),
            notify_on_turn=bool(getattr(game_class, "notify_on_turn", False)),
        )
