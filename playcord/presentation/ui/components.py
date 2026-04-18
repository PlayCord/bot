"""Unified UI component models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TextDisplay:
    text: str


@dataclass(frozen=True, slots=True)
class Media:
    data: bytes | str


@dataclass(frozen=True, slots=True)
class Button:
    label: str | None = None
    custom_id: str | None = None
    style: str = "secondary"
    emoji: str | None = None
    disabled: bool = False


@dataclass(frozen=True, slots=True)
class SelectOption:
    label: str
    value: str
    default: bool = False


@dataclass(frozen=True, slots=True)
class Select:
    custom_id: str
    placeholder: str | None = None
    options: tuple[SelectOption, ...] = ()
    disabled: bool = False


@dataclass(frozen=True, slots=True)
class Section:
    children: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class Container:
    children: tuple[Any, ...]
    accent_color: Any | None = None


@dataclass(frozen=True, slots=True)
class ViewLayout:
    containers: tuple[Container, ...] = ()
    accessories: tuple[Any, ...] = ()
    files: tuple[Any, ...] = field(default_factory=tuple)
