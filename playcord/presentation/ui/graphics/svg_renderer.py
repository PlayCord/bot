from __future__ import annotations

import html
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


def render_key_value_svg(
    title: str,
    rows: Iterable[tuple[str, str]],
    *,
    width: int = 960,
    row_height: int = 36,
    padding: int = 20,
) -> bytes:
    rows_list = list(rows)
    height = max(140, padding * 2 + 56 + len(rows_list) * row_height)
    y = padding + 36
    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">',
        f'<rect width="{width}" height="{height}" fill="#111827" rx="14" ry="14"/>',
        f'<text x="{padding}" y="{padding + 24}" fill="#f9fafb" font-family="Inter,Arial,sans-serif" font-size="24" font-weight="700">{html.escape(str(title))}</text>',
        f'<line x1="{padding}" y1="{padding + 38}" x2="{width - padding}" y2="{padding + 38}" stroke="#374151" stroke-width="1"/>',
    ]
    for key, value in rows_list:
        lines.append(
            f'<text x="{padding}" y="{y}" fill="#9ca3af" font-family="Inter,Arial,sans-serif" font-size="16" font-weight="600">{html.escape(str(key))}</text>',
        )
        lines.append(
            f'<text x="{width // 2}" y="{y}" fill="#f3f4f6" font-family="Inter,Arial,sans-serif" font-size="16">{html.escape(str(value))}</text>',
        )
        y += row_height
    lines.append("</svg>")
    return "".join(lines).encode("utf-8")
