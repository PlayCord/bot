"""Typed custom-id routing for component interactions."""

from __future__ import annotations

from dataclasses import dataclass


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
