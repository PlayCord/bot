"""Run blocking (e.g. DB) work off the asyncio event loop."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


async def run_in_thread(
    func: Callable[..., T],
    /,
    *args: Any,
    **kwargs: Any,
) -> T:
    """Delegate a blocking call to a worker thread (``asyncio.to_thread``)."""
    return await asyncio.to_thread(func, *args, **kwargs)
