"""The "CRAFT KIT" title: block letters leaning right (italic), in a gradient where blue dominates."""

from __future__ import annotations

import os

GLYPHS = {
    "C": [" █████", "██    ", "██    ", "██    ", " █████"],
    "R": ["█████ ", "██  ██", "█████ ", "██ ██ ", "██  ██"],
    "A": [" ████ ", "██  ██", "██████", "██  ██", "██  ██"],
    "F": ["██████", "██    ", "█████ ", "██    ", "██    "],
    "T": ["██████", "  ██  ", "  ██  ", "  ██  ", "  ██  "],
    "K": ["██  ██", "██ ██ ", "████  ", "██ ██ ", "██  ██"],
    "I": ["██", "██", "██", "██", "██"],
    " ": ["   "] * 5,
}

# Colour stops (position 0..1, RGB): sky → azure → royal blue → indigo, a touch of violet and pink at the end.
STOPS = [
    (0.00, (70, 210, 255)),
    (0.22, (40, 150, 255)),
    (0.50, (45, 95, 245)),
    (0.72, (80, 70, 235)),
    (0.88, (150, 85, 250)),
    (1.00, (240, 95, 200)),
]
SLANT = 1  # columns each row moves left from the top: the letters lean like italics


def truecolor() -> bool:
    return os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit") or os.environ.get("TERM_PROGRAM") in ("iTerm.app", "vscode", "WezTerm", "ghostty")


def colour_at(t: float) -> tuple[int, int, int]:
    t = min(1.0, max(0.0, t))
    for (p0, c0), (p1, c1) in zip(STOPS, STOPS[1:]):
        if t <= p1:
            k = (t - p0) / (p1 - p0) if p1 > p0 else 0.0
            return tuple(round(a + (b - a) * k) for a, b in zip(c0, c1))  # type: ignore[return-value]
    return STOPS[-1][1]


def fg(rgb: tuple[int, int, int]) -> str:
    if truecolor():
        return "\033[38;2;{};{};{}m".format(*rgb)
    r, g, b = (round(v / 255 * 5) for v in rgb)  # nearest colour of the 256-colour cube
    return f"\033[38;5;{16 + 36 * r + 6 * g + b}m"


def gradient(text: str, italic: bool = True, bold: bool = False) -> str:
    """Colour a line of text along the gradient."""
    chars = list(text)
    n = max(1, len(chars) - 1)
    style = ("\033[3m" if italic else "") + ("\033[1m" if bold else "")
    return "".join(f"{style}{fg(colour_at(i / n))}{ch}" if ch != " " else ch for i, ch in enumerate(chars)) + "\033[0m"


def big_lines(word: str = "CRAFT KIT") -> list[str]:
    rows = [""] * 5
    for ch in word.upper():
        glyph = GLYPHS.get(ch, GLYPHS[" "])
        for r in range(5):
            rows[r] += glyph[r] + " "
    return [" " * (SLANT * (4 - r)) + row.rstrip() for r, row in enumerate(rows)]


def render(width: int, fancy: bool, indent: int = 2) -> list[str]:
    """The title as lines ready to print: big letters when there's room, one styled line otherwise."""
    lines = big_lines()
    longest = max(len(line) for line in lines)
    if not fancy:
        return [" " * indent + "C R A F T   K I T"]
    if longest + indent > width:
        return [" " * indent + gradient("C R A F T   K I T", bold=True)]
    out = []
    for line in lines:
        cells = []
        r = len(out)
        for x, ch in enumerate(line):
            if ch == " ":
                cells.append(" ")
            else:
                # A slightly diagonal gradient: each letter shades from top-left to bottom-right.
                cells.append(f"\033[3m\033[1m{fg(colour_at((x + 2 * r) / (longest + 8)))}{ch}")
        out.append(" " * indent + "".join(cells) + "\033[0m")
    return out
