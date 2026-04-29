"""Shared SVG → PNG conversion for games."""

import cairosvg


def svg_to_png(svg_markup: str) -> bytes | None:
    return cairosvg.svg2png(bytestring=svg_markup.encode("utf-8"))
