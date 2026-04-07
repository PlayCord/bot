from __future__ import annotations

import io
import os
import unicodedata
from functools import lru_cache
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont

_BG = "#0f172a"
_BORDER = "#334155"
_HEADER_BG = "#1e293b"
_ROW_BG = "#111827"
_ALT_ROW_BG = "#172033"
_TEXT = "#e2e8f0"
_HEADER_TEXT = "#f8fafc"
_SCALE = 2
_FONT_SIZE = 14 * _SCALE
_HEADER_FONT_SIZE = 15 * _SCALE
_MIN_CELL_WIDTH = 96 * _SCALE
_CELL_PADDING_X = 16 * _SCALE
_TABLE_PADDING = 12 * _SCALE
_ROW_HEIGHT = 38 * _SCALE
_HEADER_HEIGHT = 40 * _SCALE

_TEXT_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
    "C:\\Windows\\Fonts\\segoeui.ttf",
)
_EMOJI_FONT_CANDIDATES = (
    "/System/Library/Fonts/Apple Color Emoji.ttc",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "C:\\Windows\\Fonts\\seguiemj.ttf",
)


def _font_path(candidates: Sequence[str]) -> str | None:
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


@lru_cache(maxsize=None)
def _load_font(size: int, *, emoji: bool = False) -> ImageFont.ImageFont:
    path = _font_path(_EMOJI_FONT_CANDIDATES if emoji else _TEXT_FONT_CANDIDATES)
    if path:
        kwargs = {}
        layout_enum = getattr(ImageFont, "Layout", None)
        layout_engine = getattr(layout_enum, "RAQM", None) if layout_enum is not None else None
        if layout_engine is not None:
            kwargs["layout_engine"] = layout_engine
        try:
            return ImageFont.truetype(path, size=size, **kwargs)
        except OSError:
            pass
    return ImageFont.load_default()


def _is_regional_indicator(codepoint: int) -> bool:
    return 0x1F1E6 <= codepoint <= 0x1F1FF


def _is_emoji_codepoint(codepoint: int) -> bool:
    return (
        0x1F300 <= codepoint <= 0x1FAFF
        or 0x2600 <= codepoint <= 0x27BF
        or _is_regional_indicator(codepoint)
        or codepoint in {0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x3030, 0x303D, 0x3297, 0x3299}
    )


def _split_clusters(text: str) -> list[str]:
    if not text:
        return []

    clusters: list[str] = []
    current = text[0]
    for char in text[1:]:
        codepoint = ord(char)
        prev_codepoint = ord(current[-1])
        if (
            current[-1] == "\u200d"
            or char == "\u200d"
            or char == "\ufe0f"
            or char == "\u20e3"
            or unicodedata.combining(char)
            or 0x1F3FB <= codepoint <= 0x1F3FF
            or (_is_regional_indicator(prev_codepoint) and _is_regional_indicator(codepoint) and len(current) == 1)
        ):
            current += char
            continue
        clusters.append(current)
        current = char
    clusters.append(current)
    return clusters


def _is_emoji_cluster(cluster: str) -> bool:
    return any(
        char in {"\u200d", "\ufe0f", "\u20e3"} or _is_emoji_codepoint(ord(char))
        for char in cluster
    )


def _text_bbox(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    *,
    embedded_color: bool = False,
) -> tuple[int, int, int, int]:
    kwargs = {"font": font}
    if embedded_color:
        kwargs["embedded_color"] = True
    try:
        return draw.textbbox((0, 0), text, **kwargs)
    except TypeError:
        kwargs.pop("embedded_color", None)
        return draw.textbbox((0, 0), text, **kwargs)


def _segment_metrics(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    *,
    embedded_color: bool = False,
) -> tuple[int, int]:
    bbox = _text_bbox(draw, text, font, embedded_color=embedded_color)
    width = max(int(round(draw.textlength(text, font=font))), bbox[2] - bbox[0])
    if not text.strip():
        width = max(width, max(1, font.size // 3))
    height = max(bbox[3] - bbox[1], font.size)
    return width, height


def _measure_text(draw: ImageDraw.ImageDraw, text: str, *, header: bool = False) -> tuple[int, int]:
    base_font = _load_font(_HEADER_FONT_SIZE if header else _FONT_SIZE)
    width = 0
    height = base_font.size
    for cluster in _split_clusters(text):
        use_emoji = _is_emoji_cluster(cluster)
        font = _load_font(_FONT_SIZE, emoji=True) if use_emoji else base_font
        cluster_width, cluster_height = _segment_metrics(draw, cluster, font, embedded_color=use_emoji)
        width += cluster_width
        height = max(height, cluster_height)
    return max(width, 1), max(height, base_font.size)


def _measure_cell(draw: ImageDraw.ImageDraw, text: str, *, header: bool = False) -> int:
    text_width, _ = _measure_text(draw, text, header=header)
    return max(_MIN_CELL_WIDTH, text_width + (_CELL_PADDING_X * 2))


def _draw_text_in_cell(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    x: int,
    y: int,
    cell_width: int,
    cell_height: int,
    fill: str,
    header: bool = False,
) -> None:
    base_font = _load_font(_HEADER_FONT_SIZE if header else _FONT_SIZE)
    _, total_height = _measure_text(draw, text, header=header)
    cursor_x = x + _CELL_PADDING_X
    for cluster in _split_clusters(text):
        use_emoji = _is_emoji_cluster(cluster)
        font = _load_font(_FONT_SIZE, emoji=True) if use_emoji else base_font
        segment_width, segment_height = _segment_metrics(draw, cluster, font, embedded_color=use_emoji)
        segment_y = y + max((cell_height - max(total_height, segment_height)) // 2, 0)
        kwargs = {"font": font}
        if use_emoji:
            kwargs["embedded_color"] = True
            draw.text((cursor_x, segment_y), cluster, **kwargs)
        else:
            draw.text((cursor_x, segment_y), cluster, fill=fill, **kwargs)
        cursor_x += segment_width
        if cursor_x >= x + cell_width - _CELL_PADDING_X:
            break


def render_table_as_png(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> bytes:
    safe_headers = [str(header) for header in headers] or ["Info"]
    safe_rows = [[str(cell) for cell in row] for row in rows]
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

    scratch = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(scratch)

    widths: list[int] = []
    for index in range(column_count):
        widest = _measure_cell(draw, normalized_headers[index], header=True)
        for row in normalized_rows:
            widest = max(widest, _measure_cell(draw, row[index]))
        widths.append(widest)

    table_width = sum(widths)
    width = table_width + (_TABLE_PADDING * 2)
    height = (_TABLE_PADDING * 2) + _HEADER_HEIGHT + (len(normalized_rows) * _ROW_HEIGHT)

    image = Image.new("RGBA", (width, height), _BG)
    draw = ImageDraw.Draw(image)

    table_left = _TABLE_PADDING
    table_top = _TABLE_PADDING
    table_bottom = height - _TABLE_PADDING
    table_height = height - (_TABLE_PADDING * 2)

    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=12 * _SCALE, fill=_BG)
    draw.rounded_rectangle(
        (table_left, table_top, table_left + table_width, table_top + _HEADER_HEIGHT),
        radius=10 * _SCALE,
        fill=_HEADER_BG,
    )

    y = table_top + _HEADER_HEIGHT
    for row_index in range(len(normalized_rows)):
        fill = _ROW_BG if row_index % 2 == 0 else _ALT_ROW_BG
        draw.rectangle((table_left, y, table_left + table_width, y + _ROW_HEIGHT), fill=fill)
        y += _ROW_HEIGHT

    x = table_left
    for width_index in widths[:-1]:
        x += width_index
        draw.line((x, table_top, x, table_bottom), fill=_BORDER, width=max(1, _SCALE))

    y = table_top + _HEADER_HEIGHT
    for _ in normalized_rows:
        draw.line((table_left, y, width - _TABLE_PADDING, y), fill=_BORDER, width=max(1, _SCALE))
        y += _ROW_HEIGHT

    draw.rounded_rectangle(
        (table_left, table_top, table_left + table_width, table_top + table_height),
        radius=10 * _SCALE,
        outline=_BORDER,
        width=max(1, _SCALE),
    )

    x = table_left
    for index, header in enumerate(normalized_headers):
        _draw_text_in_cell(
            draw,
            header,
            x=x,
            y=table_top,
            cell_width=widths[index],
            cell_height=_HEADER_HEIGHT,
            fill=_HEADER_TEXT,
            header=True,
        )
        x += widths[index]

    y = table_top + _HEADER_HEIGHT
    for row in normalized_rows:
        x = table_left
        for index, cell in enumerate(row):
            _draw_text_in_cell(
                draw,
                cell,
                x=x,
                y=y,
                cell_width=widths[index],
                cell_height=_ROW_HEIGHT,
                fill=_TEXT,
            )
            x += widths[index]
        y += _ROW_HEIGHT

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
