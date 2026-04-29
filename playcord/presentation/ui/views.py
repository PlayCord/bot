"""Top-level UI view abstraction and simple status view models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playcord.presentation.ui.components import Container, TextDisplay, ViewLayout
from playcord.presentation.ui.styling import PALETTE


@dataclass(frozen=True, slots=True)
class View:
    """A sendable UI view model."""

    layout: ViewLayout
    content: str | None = None

    def to_send_kwargs(self) -> dict[str, Any]:
        """Minimal transport shape used by new helpers.

        The rich component rendering path can be expanded later without
        changing the app-level callers.
        """
        payload: dict[str, Any] = {}
        if self.content is not None:
            payload["content"] = self.content
        if self.layout.files:
            payload["files"] = list(self.layout.files)
        return payload


def _single_card(
    message: str,
    *,
    title: str | None = None,
    accent_color=None,
) -> View:
    parts = []
    if title:
        parts.append(TextDisplay(f"## {title}"))
    parts.append(TextDisplay(message))
    return View(
        layout=ViewLayout(
            containers=(Container(tuple(parts), accent_color=accent_color),),
        ),
    )


@dataclass(frozen=True, slots=True)
class ErrorView(View):
    @classmethod
    def create(cls, message: str, *, title: str = "Error") -> ErrorView:
        base = _single_card(message, title=title, accent_color=PALETTE.error)
        return cls(layout=base.layout, content=base.content)


@dataclass(frozen=True, slots=True)
class UserErrorView(View):
    @classmethod
    def create(
        cls,
        message: str,
        *,
        title: str = "Something went wrong",
    ) -> UserErrorView:
        base = _single_card(message, title=title, accent_color=PALETTE.warning)
        return cls(layout=base.layout, content=base.content)


@dataclass(frozen=True, slots=True)
class InfoView(View):
    @classmethod
    def create(cls, message: str, *, title: str = "Info") -> InfoView:
        base = _single_card(message, title=title, accent_color=PALETTE.info)
        return cls(layout=base.layout, content=base.content)


@dataclass(frozen=True, slots=True)
class SuccessView(View):
    @classmethod
    def create(cls, message: str, *, title: str = "Success") -> SuccessView:
        base = _single_card(message, title=title, accent_color=PALETTE.success)
        return cls(layout=base.layout, content=base.content)


@dataclass(frozen=True, slots=True)
class LobbyView(View):
    @classmethod
    def create(cls, message: str, *, title: str = "Lobby") -> LobbyView:
        base = _single_card(message, title=title, accent_color=PALETTE.matchmaking)
        return cls(layout=base.layout, content=base.content)


@dataclass(frozen=True, slots=True)
class BoardView(View):
    @classmethod
    def create(cls, message: str, *, title: str = "Game") -> BoardView:
        base = _single_card(message, title=title, accent_color=PALETTE.game)
        return cls(layout=base.layout, content=base.content)


@dataclass(frozen=True, slots=True)
class StatsView(View):
    @classmethod
    def create(cls, message: str, *, title: str = "Stats") -> StatsView:
        base = _single_card(message, title=title, accent_color=PALETTE.primary)
        return cls(layout=base.layout, content=base.content)
