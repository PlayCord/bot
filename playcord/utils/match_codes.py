"""Public match codes for thread titles and /replay (distinct from internal match_id)."""

import secrets

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
