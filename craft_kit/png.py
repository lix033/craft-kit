"""Comparing screenshots without dependencies: a small PNG reader (8-bit, non-interlaced, the kind
browsers write) and a grid similarity. Uses Pillow instead when it's installed."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Optional

MAX_ROWS = 2400  # compare the top of long pages; enough for the layout, quick in pure Python
COLS = 64
TOLERANCE = 32  # a cell matches when no channel differs by more than this


class Grid:
    def __init__(self, width: int, height: int, cells: list[list[tuple[int, int, int]]]):
        self.width, self.height, self.cells = width, height, cells

    def blank(self) -> bool:
        first = self.cells[0][0] if self.cells and self.cells[0] else None
        return all(c == first for row in self.cells for c in row)


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def _grid_pure(path: Path) -> Optional[Grid]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, idat, palette = 8, [], b""
    width = height = depth = ctype = interlace = 0
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos : pos + 8])
        body = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR" and len(body) >= 13:
            width, height, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body[:13])
        elif kind == b"PLTE":
            palette = body
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
    if depth != 8 or interlace or not channels or width <= 0 or height <= 0 or width > 20_000:
        return None
    rows = min(height, MAX_ROWS)
    stride = width * channels
    raw = zlib.decompressobj().decompress(b"".join(idat), (stride + 1) * rows)
    step = max(1, width // COLS)
    grid_rows = max(1, rows * COLS // width) if width >= COLS else rows
    want = {min(rows - 1, int((r + 0.5) * rows / grid_rows)) for r in range(grid_rows)}
    cols = [min(width - 1, c * step + step // 2) for c in range(min(COLS, width))]
    prev = bytearray(stride)
    cells: list[list[tuple[int, int, int]]] = []
    for y in range(rows):
        start = y * (stride + 1)
        if start + stride + 1 > len(raw):
            break
        f = raw[start]
        line = bytearray(raw[start + 1 : start + 1 + stride])
        if f == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                up_left = prev[i - channels] if i >= channels else 0
                line[i] = (line[i] + _paeth(left, prev[i], up_left)) & 255
        if y in want:
            row = []
            for x in cols:
                o = x * channels
                if ctype == 3:
                    k = line[o] * 3
                    px = tuple(palette[k : k + 3]) if k + 3 <= len(palette) else (0, 0, 0)
                elif channels <= 2:
                    px = (line[o],) * 3
                else:
                    px = (line[o], line[o + 1], line[o + 2])
                row.append(px)  # type: ignore[arg-type]
            cells.append(row)
        prev = line
    return Grid(width, height, cells) if cells else None


def _grid_pillow(path: Path) -> Optional[Grid]:
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return None
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        h2 = min(h, MAX_ROWS)
        im = im.crop((0, 0, w, h2))
        cols = min(COLS, w)
        rows = max(1, h2 * cols // w)
        small = im.resize((cols, rows))
        px = small.load()
        return Grid(w, h, [[px[x, y] for x in range(cols)] for y in range(rows)])


def grid(path: Path) -> Optional[Grid]:
    try:
        return _grid_pillow(path) or _grid_pure(path)
    except (OSError, ValueError, zlib.error, struct.error):
        return None


def similarity(a: Grid, b: Grid) -> float:
    """Percent of grid cells that match; rows only one image has count as different."""
    rows = max(len(a.cells), len(b.cells))
    cols = min(len(a.cells[0]), len(b.cells[0])) if a.cells and b.cells else 0
    if rows == 0 or cols == 0:
        return 0.0
    same = 0
    for y in range(min(len(a.cells), len(b.cells))):
        for x in range(cols):
            pa, pb = a.cells[y][x], b.cells[y][x]
            if max(abs(pa[0] - pb[0]), abs(pa[1] - pb[1]), abs(pa[2] - pb[2])) <= TOLERANCE:
                same += 1
    return 100.0 * same / (rows * cols)
