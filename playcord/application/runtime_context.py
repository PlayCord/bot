"""Process-wide application container binding for non-DI call sites."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playcord.application.container import ApplicationContainer

_container: ApplicationContainer | None = None


def bind_application_container(container: ApplicationContainer) -> None:
    global _container
    _container = container


def try_get_container() -> ApplicationContainer | None:
    return _container


def get_container() -> ApplicationContainer:
    if _container is None:
        msg = (
            "Application container is not bound; call bind_application_container first"
        )
        raise RuntimeError(msg)
    return _container
