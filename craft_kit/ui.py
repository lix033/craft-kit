"""A minimal terminal interface: one line per step, a live feed of what's happening, one live line
while something runs. Each stage has its colour (study sky, build blue, refine violet, check amber,
ready green); NO_COLOR, a pipe or TERM=dumb give plain text, CRAFT_FEED=0 keeps only the live line."""

from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from typing import Optional

from . import banner

ICONS = {"done": ("✓", "32"), "run": ("●", "36"), "todo": ("○", "2"), "fail": ("✗", "31"), "wait": ("?", "33"), "skip": ("–", "2")}
FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

RGB = tuple  # (r, g, b)

# The stages of the loop, each with its colour.
STAGES: dict = {
    "study": (70, 210, 255),
    "build": (60, 125, 255),
    "refine": (165, 95, 255),
    "check": (255, 185, 60),
    "ready": (80, 220, 130),
}
# Step lines whose name isn't a stage say which stage they belong to.
STEP_STAGE = {"runs": "study", "inside": "study", "new": "ready", "answer": "build", "open": "ready", "skill": "ready"}

# What the builder does, by kind: icon, verb, colour. None = dim.
KINDS: dict = {
    "read": ("◇", "read", (120, 200, 255)),
    "edit": ("✎", "edit", (90, 225, 140)),
    "write": ("✚", "write", (60, 235, 170)),
    "run": ("❯", "run", (255, 200, 80)),
    "search": ("⌕", "search", (205, 140, 255)),
    "web": ("◎", "web", (80, 165, 255)),
    "plan": ("☰", "plan", (245, 115, 200)),
    "agent": ("◆", "agent", (150, 160, 255)),
    "tool": ("▸", "tool", (180, 180, 200)),
    "fail": ("✗", "failed", (240, 85, 95)),
    "say": ("“", "", None),
    "out": ("·", "", None),
}


def _tty(stream) -> bool:
    try:
        return stream.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
    except (AttributeError, ValueError):
        return False


def elapsed(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60}m{s % 60:02d}s" if s >= 60 else f"{s}s"


def clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


def fit(text: str, room: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= room else text[: max(0, room - 1)] + "…"


def stage_of(name: str) -> Optional[str]:
    return name if name in STAGES else STEP_STAGE.get(name)


def _mix(a: RGB, b: RGB, k: float) -> RGB:
    return tuple(round(x + (y - x) * k) for x, y in zip(a, b))


class UI:
    def __init__(self, stream=None):
        self.out = stream or sys.stderr
        self.fancy = _tty(self.out)
        self.feed = os.environ.get("CRAFT_FEED", "1").lower() not in ("0", "off", "no", "false")
        self._lock = threading.Lock()
        self._live: Live | None = None

    # colours ---------------------------------------------------------------
    def c(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.fancy else text

    def rgb(self, colour: Optional[RGB], text: str, bold: bool = False, italic: bool = False, dim: bool = False) -> str:
        if not self.fancy or not text:
            return text
        style = ("\033[1m" if bold else "") + ("\033[3m" if italic else "") + ("\033[2m" if dim else "")
        return f"{style}{banner.fg(colour) if colour else ''}{text}\033[0m"

    def dim(self, t: str) -> str:
        return self.c("2", t)

    def bold(self, t: str) -> str:
        return self.c("1", t)

    def red(self, t: str) -> str:
        return self.c("31", t)

    def green(self, t: str) -> str:
        return self.c("32", t)

    def yellow(self, t: str) -> str:
        return self.c("33", t)

    def width(self) -> int:
        return max(40, min(shutil.get_terminal_size((80, 20)).columns, 100))

    # output ------------------------------------------------------------------
    def say(self, text: str = "") -> None:
        with self._lock:
            if self._live is not None:
                self._live.clear()
            print(text, file=self.out, flush=True)

    def header(self, name: str, right: str) -> None:
        w = self.width()
        left = f"craft · {name}"
        gap = max(1, w - len(left) - len(right) - 2)
        self.say(f" {self.bold(left)}{' ' * gap}{self.dim(right)}")

    def stage(self, name: str, detail: str = "") -> None:
        """A coloured rule that opens a stage: ` ▍build  claude · turn 3 ─────────`."""
        colour = STAGES.get(name)
        detail = fit(detail, self.width() - len(name) - 12)
        rule = "─" * max(3, self.width() - len(name) - len(detail) - 8)
        if not self.fancy:
            self.say(f"\n -- {name}  {detail}".rstrip())
            return
        self.say("")
        self.say(f" {self.rgb(colour, '▍' + name, bold=True)}  {detail}{' ' if detail else ''}{self.rgb(colour, rule, dim=True)}")

    def step(self, state: str, name: str, detail: str = "", stage: Optional[str] = None) -> None:
        icon, code = ICONS.get(state, ICONS["todo"])
        quiet = state in ("todo", "skip")
        detail = self.dim(detail) if quiet else detail
        colour = STAGES.get(stage or stage_of(name) or "")
        label = f"{name:<7}"
        label = self.dim(label) if quiet else (self.rgb(colour, label, bold=True) if colour else label)
        self.say(f" {self.c(code, icon)} {label} {detail}".rstrip())

    def note(self, text: str) -> None:
        for line in text.splitlines() or [""]:
            self.say(f"   {self.dim('│')} {line}")

    def error(self, text: str) -> None:
        self.say(f" {self.red('✗')} {text}")

    def warn(self, text: str) -> None:
        self.say(f" {self.yellow('!')} {text}")

    def report(self, e) -> None:
        """A CraftError: what went wrong, then what to do (its guide, or its one-line fix)."""
        self.error(e.message)
        if getattr(e, "guide", None):
            e.guide(self)
        elif getattr(e, "fix", ""):
            for line in e.fix.splitlines():
                self.say(f"   {self.dim(line)}")

    def live(self, label: str, stage: Optional[str] = None) -> "Live":
        return Live(self, label, stage)

    # input -------------------------------------------------------------------
    def interactive(self) -> bool:
        return sys.stdin.isatty() and self.fancy

    def ask(self, prompt: str) -> str:
        with self._lock:
            if self._live is not None:
                self._live.clear()
        try:
            return input(f" {self.c('33', '?')} {prompt} ").strip()
        except EOFError:
            return ""

    def choose(self, question: str, choices: list[str]) -> str:
        self.say(f" {self.c('33', '?')} {question}")
        for i, ch in enumerate(choices, 1):
            self.say(f"     {self.bold(str(i))}  {ch}")
        raw = self.ask("number, or your own answer:")
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        return raw


class Live:
    """While something runs: a feed of what it does (one line per action, kept on screen) above a
    single line that redraws in place (spinner, shimmering label, elapsed time, latest activity)."""

    def __init__(self, ui: UI, label: str, stage: Optional[str] = None):
        self.ui = ui
        self.label = label
        self.colour: RGB = STAGES.get(stage or "", (150, 160, 255))
        self.detail = ""
        self.start = time.monotonic()
        self.counts: dict = {}
        self._last_event = ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "Live":
        if self.ui.fancy:
            self.ui._live = self
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        else:
            print(f"   … {self.label}", file=self.ui.out, flush=True)
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        with self.ui._lock:
            self.clear()
            self.ui._live = None

    def update(self, detail: str) -> None:
        self.detail = " ".join(detail.split())

    def event(self, kind: str, text: str, count: bool = True) -> None:
        """One action, kept in the feed: `   1:42 ✎ edit    src/main.rs`."""
        text = " ".join(text.split())
        if not text:
            return
        self.update(text)
        key = f"{kind}\0{text}"
        if key == self._last_event:  # the same line twice in a row says nothing new
            return
        self._last_event = key
        if count and kind not in ("say", "out"):
            self.counts[kind] = self.counts.get(kind, 0) + 1
        if not self.ui.feed:
            return
        icon, verb, colour = KINDS.get(kind, KINDS["tool"])
        stamp = clock(time.monotonic() - self.start)
        head = f"{icon} {verb:<7}" if verb else f"{icon} "
        room = self.ui.width() - len(stamp) - len(head) - 6
        body = fit(text, room)
        u = self.ui
        if kind in ("say", "out"):
            line = f"   {u.dim(stamp)} {u.dim(head)}{u.rgb(None, body, italic=kind == 'say', dim=True)}"
        else:
            line = f"   {u.dim(stamp)} {u.rgb(colour, head, bold=True)}{u.rgb(colour, body) if kind == 'fail' else body}"
        u.say(line)

    def tally(self) -> str:
        """`2m14s · 18 actions: 6 edit, 5 read, 4 run`."""
        counts = {k: n for k, n in self.counts.items() if k != "fail"}
        total = sum(counts.values())
        out = elapsed(time.monotonic() - self.start)
        if total:
            parts = sorted(counts.items(), key=lambda kv: -kv[1])
            out += f" · {total} action{'s' if total > 1 else ''}: " + ", ".join(f"{n} {KINDS.get(k, KINDS['tool'])[1] or k}" for k, n in parts)
        if self.counts.get("fail"):
            out += f" · {self.counts['fail']} failed"
        return out

    def clear(self) -> None:
        if self.ui.fancy:
            self.ui.out.write("\r\033[2K")
            self.ui.out.flush()

    def _shimmer(self, text: str, i: int) -> str:
        """The label in its stage colour, a bright band sweeping across it."""
        base = _mix(self.colour, (40, 40, 60), 0.25)
        n = len(text) + 8
        pos = (i * 0.6) % n - 4
        cells = []
        for x, ch in enumerate(text):
            k = max(0.0, 1.0 - abs(x - pos) / 4.0)
            cells.append(f"{banner.fg(_mix(base, (255, 255, 255), 0.7 * k))}{ch}")
        return "\033[1m" + "".join(cells) + "\033[0m"

    def _spin(self) -> None:
        i = 0
        while not self._stop.wait(0.1):
            i += 1
            u = self.ui
            frame = FRAMES[i % len(FRAMES)]
            time_s = elapsed(time.monotonic() - self.start)
            done = sum(n for k, n in self.counts.items() if k != "fail")
            meta = f" · {time_s}" + (f" · {done}" if done else "")
            room = u.width() - 1 - 5 - len(self.label) - len(meta)
            detail = f" · {fit(self.detail, room - 3)}" if self.detail and room > 8 else ""
            text = f"   {u.rgb(self.colour, frame, bold=True)} {self._shimmer(self.label, i)}{u.dim(meta)}{u.dim(detail)}"
            with u._lock:
                u.out.write("\r\033[2K" + text)
                u.out.flush()
