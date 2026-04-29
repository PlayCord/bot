"""Shared response helpers for interactions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import discord

if TYPE_CHECKING:
    from playcord.presentation.ui.views import View


def schedule_delete(message: Any, delay: float | None) -> None:
    if message is None or delay is None or delay <= 0:
        return

    async def _delete() -> None:
        try:
            await asyncio.sleep(delay)
            await message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

    try:
        asyncio.get_running_loop().create_task(_delete())
    except RuntimeError:
        return


async def respond(
    interaction: discord.Interaction,
    view: View | None = None,
    *,
    content: str | None = None,
    ephemeral: bool = False,
    delete_after: float | None = None,
) -> Any:
    payload = {"ephemeral": ephemeral}
    if view is not None:
        payload.update(view.to_send_kwargs())
    if content is not None:
        payload["content"] = content

    if interaction.response.is_done():
        message = await interaction.followup.send(**payload)
    else:
        message = await interaction.response.send_message(**payload)
    schedule_delete(message, delete_after)
    return message


"""Typed custom-id routing for component interactions."""


@dataclass(frozen=True, slots=True)
class CustomId:
    namespace: str
    action: str
    resource_id: int
    payload: str = ""

    def encode(self) -> str:
        parts = [self.namespace, self.action, str(self.resource_id)]
        if self.payload:
            parts.append(self.payload)
        return ":".join(parts)

    @classmethod
    def decode(cls, raw: str) -> CustomId:
        parts = raw.split(":", 3)
        if len(parts) < 3:
            msg = f"Invalid custom_id: {raw!r}"
            raise ValueError(msg)
        payload = parts[3] if len(parts) == 4 else ""
        return cls(
            namespace=parts[0],
            action=parts[1],
            resource_id=int(parts[2]),
            payload=payload,
        )


class InteractionRouter:
    """Simple callback registry keyed by the custom-id namespace and action."""

    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], Any] = {}

    def register(self, namespace: str, action: str, handler: Any) -> None:
        self._handlers[(namespace, action)] = handler

    def resolve(self, custom_id: str) -> tuple[CustomId, Any]:
        parsed = CustomId.decode(custom_id)
        try:
            handler = self._handlers[(parsed.namespace, parsed.action)]
        except KeyError as exc:
            msg = f"No interaction handler for {parsed.namespace}:{parsed.action}"
            raise KeyError(
                msg,
            ) from exc
        return parsed, handler
