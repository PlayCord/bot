"""Format stored JSONL replay events for display in embeds."""

from __future__ import annotations

import json
from typing import Any


def format_replay_event_line(evt: dict[str, Any]) -> str:
    """One human-readable line per replay event (Discord markdown-safe, no raw newlines)."""
    t = evt.get("type") or "?"
    if t == "move":
        mn = evt.get("move_number", "?")
        uid = evt.get("user_id")
        cmd = evt.get("command_name") or evt.get("python_callback") or "?"
        args = evt.get("arguments", {})
        if isinstance(args, dict):
            arg_s = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
        else:
            arg_s = str(args)
        if len(arg_s) > 140:
            arg_s = arg_s[:137] + "..."
        who = f"user {uid}" if uid is not None else "system"
        return f"#{mn} · {who} · `{cmd}` · {arg_s}"
    raw = json.dumps(evt, ensure_ascii=False, separators=(",", ":"))
    if len(raw) > 300:
        return raw[:297] + "..."
    return raw


def chunk_replay_lines(lines: list[str], *, per_page: int = 12, max_chars: int = 3200) -> list[str]:
    """Split lines into pages that fit a single embed description (with code fence)."""
    if not lines:
        return ["(no lines)"]
    pages: list[str] = []
    buf: list[str] = []
    char_count = 0
    for line in lines:
        line_len = len(line) + 1
        if buf and (len(buf) >= per_page or char_count + line_len > max_chars):
            pages.append("\n".join(buf))
            buf = []
            char_count = 0
        buf.append(line)
        char_count += line_len
    if buf:
        pages.append("\n".join(buf))
    return pages
