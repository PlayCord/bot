"""Typed custom-id routing for component interactions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
            raise ValueError(f"Invalid custom_id: {raw!r}")
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
            raise KeyError(
                f"No interaction handler for {parsed.namespace}:{parsed.action}"
            ) from exc
        return parsed, handler
