"""Top-level UI view abstraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playcord.presentation.ui.components import ViewLayout


@dataclass(frozen=True, slots=True)
class View:
    """A sendable UI view model."""

    layout: ViewLayout
    content: str | None = None

    def to_send_kwargs(self) -> dict[str, Any]:
        """
        Minimal transport shape used by new helpers.

        The rich component rendering path can be expanded later without
        changing the app-level callers.
        """

        payload: dict[str, Any] = {}
        if self.content is not None:
            payload["content"] = self.content
        if self.layout.files:
            payload["files"] = list(self.layout.files)
        return payload
