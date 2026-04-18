"""Rating service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RatingService:
    repository: Any

    def get_for_user(self, user_id: int) -> Any | None:
        return self.repository.get(user_id)
