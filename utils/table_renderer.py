from __future__ import annotations

import html
from typing import Sequence

from utils.svg_utils import svg_to_png

_BG = "#0f172a"
_BORDER = "#334155"
_HEADER_BG = "#1e293b"
_ROW_BG = "#111827"
_ALT_ROW_BG = "#172033"
_TEXT = "#e2e8f0"
_HEADER_TEXT = "#f8fafc"
_FONT = "DejaVu Sans, sans-serif"
_FONT_SIZE = 14
_CHAR_WIDTH = 8.4
_CELL_PADDING_X = 16
_TABLE_PADDING = 12
_ROW_HEIGHT = 38
_HEADER_HEIGHT = 40


def _measure_cell(text: str) -> int:
    return max(96, int(len(text) * _CHAR_WIDTH) + (_CELL_PADDING_X * 2))


def render_table_as_png(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> bytes:
    safe_headers = [str(header) for header in headers] or ["Info"]
    safe_rows = [[str(cell) for cell in row] for row in rows]
    # Build a list of column counts (header count plus each row's cell count)
    # Use max(iterable, default=0) to avoid TypeError when there are no rows.
    lengths = [len(safe_headers)] + [len(row) for row in safe_rows]
    column_count = max(lengths, default=0)

    if column_count == 0:
        safe_headers = ["Info"]
        column_count = 1

    normalized_headers = [
        safe_headers[index] if index < len(safe_headers) else ""
        for index in range(column_count)
    ]
    normalized_rows = [
        [row[index] if index < len(row) else "" for index in range(column_count)]
        for row in safe_rows
    ]

    widths: list[int] = []
    for index in range(column_count):
        widest = _measure_cell(normalized_headers[index])
        for row in normalized_rows:
            widest = max(widest, _measure_cell(row[index]))
        widths.append(widest)

    table_width = sum(widths)
    width = table_width + (_TABLE_PADDING * 2)
    height = (_TABLE_PADDING * 2) + _HEADER_HEIGHT + (len(normalized_rows) * _ROW_HEIGHT)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" rx="12" fill="{_BG}"/>',
        (
            f'<rect x="{_TABLE_PADDING}" y="{_TABLE_PADDING}" width="{table_width}" height="{_HEADER_HEIGHT}" '
            f'rx="10" fill="{_HEADER_BG}"/>'
        ),
    ]

    y = _TABLE_PADDING + _HEADER_HEIGHT
    for row_index in range(len(normalized_rows)):
        fill = _ROW_BG if row_index % 2 == 0 else _ALT_ROW_BG
        parts.append(
            f'<rect x="{_TABLE_PADDING}" y="{y}" width="{table_width}" height="{_ROW_HEIGHT}" fill="{fill}"/>'
        )
        y += _ROW_HEIGHT

    x = _TABLE_PADDING
    for width_index in widths[:-1]:
        x += width_index
        parts.append(
            f'<line x1="{x}" y1="{_TABLE_PADDING}" x2="{x}" y2="{height - _TABLE_PADDING}" '
            f'stroke="{_BORDER}" stroke-width="1"/>'
        )

    y = _TABLE_PADDING + _HEADER_HEIGHT
    for _ in normalized_rows:
        parts.append(
            f'<line x1="{_TABLE_PADDING}" y1="{y}" x2="{width - _TABLE_PADDING}" y2="{y}" '
            f'stroke="{_BORDER}" stroke-width="1"/>'
        )
        y += _ROW_HEIGHT

    parts.append(
        f'<rect x="{_TABLE_PADDING}" y="{_TABLE_PADDING}" width="{table_width}" '
        f'height="{height - (_TABLE_PADDING * 2)}" rx="10" fill="none" stroke="{_BORDER}" stroke-width="1"/>'
    )

    x = _TABLE_PADDING
    for index, header in enumerate(normalized_headers):
        text_x = x + _CELL_PADDING_X
        text_y = _TABLE_PADDING + (_HEADER_HEIGHT / 2) + 1
        parts.append(
            f'<text x="{text_x}" y="{text_y}" fill="{_HEADER_TEXT}" '
            f'font-family="{_FONT}" font-size="{_FONT_SIZE}" font-weight="700" '
            f'dominant-baseline="middle">{html.escape(header)}</text>'
        )
        x += widths[index]

    y = _TABLE_PADDING + _HEADER_HEIGHT
    for row in normalized_rows:
        x = _TABLE_PADDING
        for index, cell in enumerate(row):
            text_x = x + _CELL_PADDING_X
            text_y = y + (_ROW_HEIGHT / 2) + 1
            parts.append(
                f'<text x="{text_x}" y="{text_y}" fill="{_TEXT}" '
                f'font-family="{_FONT}" font-size="{_FONT_SIZE}" dominant-baseline="middle">'
                f"{html.escape(cell)}</text>"
            )
            x += widths[index]
        y += _ROW_HEIGHT

    parts.append("</svg>")
    png = svg_to_png("".join(parts))
    if png is None:
        raise ValueError("SVG table rendering failed")
    return png
