#!/usr/bin/env python3
"""Renders the app mark to the raster icons in ../public/.

Run: uv run python frontend/icons/render.py

(through uv, not a bare `python3`: this uses 3.10+ syntax and macOS still ships 3.9.)

Why this exists rather than an SVG: iOS ignores an SVG `apple-touch-icon`, so the home-screen
case needs PNGs whatever else we do. And why it's hand-rolled rather than a call out to a
converter: the repo has no image dependency and needs none for this. The mark is one polyline
with round caps and joins, so its outline is exactly "every point within half a stroke-width
of the line" -- a distance test, which is a few lines, exact, and gives the same bytes on any
machine. `rsvg-convert` isn't installed here, and macOS's `qlmanage` renders this file into
the corner of the canvas rather than filling it.

Keep the path in step with ../public/favicon.svg and ../src/components/AppMark.tsx.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

# The mark, in the 16-unit space the favicon is drawn in: "M2 8.5 h2.6 l1.7-4 l2.2 6.6
# l1.4-2.6 H14", flattened to points.
POINTS: list[tuple[float, float]] = [
    (2.0, 8.5),
    (4.6, 8.5),
    (6.3, 4.5),
    (8.5, 11.1),
    (9.9, 8.5),
    (14.0, 8.5),
]
STROKE_HALF_WIDTH = 1.0  # stroke-width="2"
VIEWBOX = 16.0

BACKGROUND = (0xF3, 0xF4, 0xF9)  # the app's light background
MARK = (0xEF, 0x54, 0x6C)  # --group-heart at its light value

# The mark occupies the middle 56%: a maskable icon may be cropped to a circle, and iOS
# rounds the corners, so the drawing has to clear them.
INSET_FRACTION = 0.22
SUPERSAMPLE = 4  # 4x4 per pixel, which is enough to keep the round caps smooth

OUTPUTS = {
    "apple-touch-icon.png": 180,
    "icon-192.png": 192,
    "icon-512.png": 512,
}


def distance_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    """Shortest distance from a point to a line segment."""
    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy
    if length_squared == 0.0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / length_squared
    t = max(0.0, min(1.0, t))
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


def coverage(u: float, v: float) -> float:
    """How much of the sample's neighbourhood the stroke covers, via the distance test.

    Round caps and joins are what make this exact: the stroked outline of such a path is the
    set of points within STROKE_HALF_WIDTH of the polyline, with no mitre or square-cap
    geometry to special-case.
    """
    best = min(
        distance_to_segment(u, v, *POINTS[i], *POINTS[i + 1]) for i in range(len(POINTS) - 1)
    )
    return 1.0 if best <= STROKE_HALF_WIDTH else 0.0


def render(size: int) -> bytes:
    inset = size * INSET_FRACTION
    scale = (size - inset * 2) / VIEWBOX
    step = 1.0 / SUPERSAMPLE
    samples = SUPERSAMPLE * SUPERSAMPLE

    rows = bytearray()
    for y in range(size):
        rows.append(0)  # PNG filter type 0 (None) for this scanline
        for x in range(size):
            hits = 0
            for sy in range(SUPERSAMPLE):
                v = ((y + (sy + 0.5) * step) - inset) / scale
                for sx in range(SUPERSAMPLE):
                    u = ((x + (sx + 0.5) * step) - inset) / scale
                    hits += coverage(u, v)
            alpha = hits / samples
            rows.extend(
                round(background + (mark - background) * alpha)
                for background, mark in zip(BACKGROUND, MARK, strict=True)
            )
    return bytes(rows)


def write_png(path: Path, size: int, raw: bytes) -> None:
    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    # 8-bit RGB, no alpha: iOS composites a transparent home-screen icon onto black.
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    public = Path(__file__).resolve().parent.parent / "public"
    for name, size in OUTPUTS.items():
        write_png(public / name, size, render(size))
        print(f"wrote {name} ({size}x{size})")


if __name__ == "__main__":
    main()
