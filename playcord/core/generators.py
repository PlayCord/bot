"""Random string and name generation helpers."""

from __future__ import annotations

import random
import secrets

BOT_FIRST_NAMES = [
    "Mary",
    "Alex",
    "Sam",
    "Jordan",
    "Taylor",
    "Avery",
    "Riley",
    "Casey",
    "Morgan",
    "Jamie",
    "Quinn",
    "Harper",
    "Skyler",
    "Parker",
    "Reese",
    "Rowan",
]


def generate_bot_name(used_names: set[str] | None = None) -> str:
    """Generate a unique display name for a bot in the form "<Name> (Bot)"."""
    used_names = used_names or set()
    shuffled = BOT_FIRST_NAMES[:]
    random.shuffle(shuffled)
    for first_name in shuffled:
        candidate = f"{first_name} (Bot)"
        if candidate not in used_names:
            return candidate
    suffix = random.randint(100, 999)
    return f"Bot {suffix} (Bot)"


_MATCH_CODE_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
_MATCH_CODE_LEN = 8


def generate_match_code() -> str:
    """Return a random ``_MATCH_CODE_LEN``-character string from 0-9 and a-z."""
    return "".join(secrets.choice(_MATCH_CODE_ALPHABET) for _ in range(_MATCH_CODE_LEN))


def is_match_code_token(s: str) -> bool:
    """True if ``s`` looks like a public match code (length and charset)."""
    if len(s) != _MATCH_CODE_LEN:
        return False
    return all(c in _MATCH_CODE_ALPHABET for c in s)
