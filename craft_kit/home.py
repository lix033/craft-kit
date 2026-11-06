"""The home screen: `craft` on its own. The title, past creations to browse with the arrow keys,
and a new project in a few questions. Actions run in the normal terminal, then come back here."""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from . import __version__, banner, proc, tables
from .ui import UI
from .workspace import CraftError, Project, forget, parse_target, projects_dir, read_json, remembered, slug, STATE

ALT_ON, ALT_OFF = "\033[?1049h", "\033[?1049l"
DESCRIPTION = [
    ("Study", "looks at the original: screenshots, what it prints, its files (Deep mode)"),
    ("Build", "your agent (Claude Code, Codex, Gemini) writes a new version in app/"),
    ("Check", "compares it with the original and measures what differs"),
    ("Refine", "sends the differences back until every check passes"),
]
HIDE, SHOW = "\033[?25l", "\033[?25h"
CLEAR = "\033[H\033[2J"


# --- keys -----------------------------------------------------------------------------------------

def read_key() -> str:
    """One key press: up, down, enter, esc, backspace, or the character itself."""
    if os.name == "nt":
        import msvcrt  # type: ignore

        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(msvcrt.getwch(), "")
        if ch == "\x03":
            raise KeyboardInterrupt
        return {"\r": "enter", "\x1b": "esc", "\x08": "backspace"}.get(ch, ch)
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = os.read(fd, 1)
        if ch == b"\x1b":
            seq = b""
            while len(seq) < 2 and select.select([fd], [], [], 0.04)[0]:
                seq += os.read(fd, 1)
            return {b"[A": "up", b"[B": "down", b"[C": "right", b"[D": "left", b"OA": "up", b"OB": "down"}.get(seq, "esc")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    if ch == b"\x03":
        raise KeyboardInterrupt
    if ch in (b"\r", b"\n"):
        return "enter"
    if ch in (b"\x7f", b"\x08"):
        return "backspace"
    return ch.decode("utf-8", "replace")


# --- what a project looks like in the list -------------------------------------------------------

def ago(iso: str) -> str:
    try:
        t = time.mktime(time.strptime(iso, "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, OverflowError):
        return ""
    s = max(0, int(time.time() - t))
    for unit, size in (("d", 86400), ("h", 3600), ("min", 60)):
        if s >= size:
            return f"{s // size} {unit} ago"
    return "just now"


def summary(path: str) -> dict:
    state = read_json(Path(path) / STATE)
    if not isinstance(state, dict):
        return {"path": path, "name": Path(path).name, "missing": True}
    steps = state.get("steps") or {}
    if steps.get("ready") == "done":
        badge = ("done", "ready")
    elif steps.get("ready") == "failed":
        badge = ("fail", "not yet")
    elif steps.get("build") == "waiting":
        badge = ("wait", "question")
    elif steps.get("build") in ("running", "paused", "done"):
        badge = ("run", "building")
    elif steps.get("study") == "done":
        badge = ("run", "studied")
    else:
        badge = ("todo", "new")
    return {
        "path": path,
        "name": str(state.get("name") or Path(path).name),
        "request": str(state.get("request", "")),
        "kind": str(state.get("kind", "")),
        "stack": str(state.get("stack", "")),
        "badge": badge,
        "missing": False,
    }


def nearby() -> list[str]:
    """Projects in the current folder and the projects folder that the list doesn't know yet."""
    found = []
    for base in {Path.cwd(), projects_dir()}:
        try:
            for child in base.iterdir():
                if (child / STATE).is_file():
                    found.append(str(child.resolve()))
        except OSError:
            continue
    if (Path.cwd() / STATE).is_file():
        found.append(str(Path.cwd().resolve()))
    return found


# --- the screen -------------------------------------------------------------------------------------

class Home:
    def __init__(self, ui: UI, loop: Callable, show_status: Callable):
        self.ui = ui
        self.loop = loop  # cli.loop(project, ui, message, agent)
        self.show_status = show_status
        self.out = ui.out

    def w(self, text: str) -> None:
        self.out.write(text)
        self.out.flush()

    def line(self, text: str = "") -> None:
        self.w(text + "\n")

    def title(self, describe: bool = False) -> None:
        self.w(CLEAR)
        self.line()
        for row in banner.render(self.ui.width(), self.ui.fancy):
            self.line(row)
        self.line("  " + (banner.gradient(f"study → build → check → refine · v{__version__}") if self.ui.fancy else f"study → build → check → refine · v{__version__}"))
        self.line()
        if describe:
            self.describe()
        from . import agent

        if not agent.installed():  # say it before anyone starts a project
            ui = self.ui
            self.line(f"  {ui.yellow('!')} No coding agent found: install Claude Code, Codex or Gemini CLI {ui.dim('(details: craft agents)')}")
            self.line()

    def describe(self) -> None:
        """What the tool does, in a few lines, on the home screen."""
        ui = self.ui
        rows = shutil.get_terminal_size((80, 24)).lines
        if rows < 30 or ui.width() < 70:  # a small window keeps one line, so the list stays visible
            self.line(ui.dim("  Rebuilds any software with your coding agent, checked against the original."))
            self.line()
            return
        self.line("  Recreate a website, CLI, app or game, or build a new one, with your coding agent,")
        self.line("  and prove the result with real checks. Four steps, run for you:")
        self.line()
        for i, (name, text) in enumerate(DESCRIPTION):
            label = f"{i + 1} {name:<7}"
            if ui.fancy:
                label = f"\033[3m\033[1m{banner.fg(banner.colour_at(0.1 + i * 0.22))}{label}\033[0m"
            self.line(f"    {label} {ui.dim(text)}")
        self.line()

    def menu(self, draw_top: Callable[[], None], items: list[str], footer: str, start: int = 0, keys: str = "") -> tuple[str, int]:
        """Draw a list and let the person move through it. Returns (key, index): key is "enter",
        "esc", or one of `keys`."""
        i = min(max(0, start), max(0, len(items) - 1))
        while True:
            draw_top()
            rows = shutil.get_terminal_size((80, 24)).lines
            room = max(3, rows - (22 if rows >= 30 else 15))
            first = min(max(0, i - room // 2), max(0, len(items) - room))
            if first > 0:
                self.line(self.ui.dim("    ↑ more"))
            for k in range(first, min(len(items), first + room)):
                if k == i:
                    self.line("  " + banner.gradient("›", italic=False, bold=True) + " " + self.ui.bold(items[k]) if self.ui.fancy else f"  > {items[k]}")
                else:
                    self.line(f"    {items[k]}")
            if first + room < len(items):
                self.line(self.ui.dim("    ↓ more"))
            self.line()
            self.line(self.ui.dim(f"  {footer}"))
            key = read_key()
            if key in ("up", "k") and items:
                i = (i - 1) % len(items)
            elif key in ("down", "j") and items:
                i = (i + 1) % len(items)
            elif key in ("enter", "right") and items:
                return "enter", i
            elif key in ("esc", "q", "left"):
                return "esc", i
            elif key and key in keys:
                return key, i

    # actions run in the normal screen, so their output stays in the terminal's history
    def outside(self, action: Callable[[], object]) -> None:
        self.w(ALT_OFF + SHOW)
        pause = True
        try:
            pause = action() is not False
        except CraftError as e:
            self.ui.report(e)
        except KeyboardInterrupt:
            self.ui.say(f"\n   {self.ui.dim('stopped')}")
        if pause:
            self.ui.say("")
            self.ui.ask(self.ui.dim("press Enter to go back"))
        self.w(ALT_ON + HIDE)

    def run(self) -> int:
        self.w(ALT_ON + HIDE)
        try:
            self.projects()
        except KeyboardInterrupt:
            pass
        finally:
            self.w(ALT_OFF + SHOW)
        return 0

    def projects(self) -> None:
        known = [i["path"] for i in remembered()]
        for path in nearby():
            if path not in known:
                known.append(path)
        sel = 0
        while True:
            entries = [summary(p) for p in known]
            opened = {i["path"]: i.get("opened", "") for i in remembered()}
            width = self.ui.width()
            labels = [self.ui.c("33", "+ New project")]
            for e in entries:
                if e["missing"]:
                    labels.append(self.ui.dim(f"{e['name'][:28]:<28}  folder not found"))
                    continue
                icon, code = {"done": ("✓", "32"), "fail": ("✗", "31"), "wait": ("?", "33"), "run": ("●", "36"), "todo": ("○", "2")}[e["badge"][0]]
                meta = f"{e['kind']} · {e['stack']}"
                label = f"{e['name'][:28]:<28}  {self.ui.c(code, icon)} {e['badge'][1]:<9} {self.ui.dim(f'{meta[:26]:<26}')}"
                when = ago(opened.get(e["path"], ""))
                if when and width >= 90:
                    label += "  " + self.ui.dim(when)
                labels.append(label)

            def top() -> None:
                self.title(describe=True)
                self.line(self.ui.bold("  Your creations") + self.ui.dim(f"  ({len(entries)})") if entries else self.ui.bold("  Nothing made yet: start with a new project"))
                self.line()

            key, sel = self.menu(top, labels, "↑↓ move · ⏎ open · n new · x remove from list · q quit", sel, keys="nx")
            if key == "esc":
                return
            if key == "n" or (key == "enter" and sel == 0):
                made = self.new_project()
                if made:
                    known = [made, *[k for k in known if k != made]]
                    sel = 1
                    self.project(made)
                continue
            if sel == 0:
                continue
            entry = entries[sel - 1]
            if key == "x":
                forget(entry["path"])
                known.remove(entry["path"])
                sel = max(0, sel - 1)
            elif key == "enter" and not entry["missing"]:
                self.project(entry["path"])

    def project(self, path: str) -> None:
        sel = 0
        while True:
            try:
                p = Project.open(Path(path))
            except CraftError:
                return
            actions = []
            if p.pending_questions():
                actions.append(("answer", "Answer the builder's questions"))
            ready = p.state["steps"].get("ready") == "done"
            actions.append(("run", "Continue building" if not ready else "Build again"))
            actions += [("change", "Ask for a change…"), ("open", "Open the result"), ("check", "Check it again"), ("folder", "Show the folder"), ("back", "Back")]

            def top() -> None:
                self.title()
                self.show_status(p, self.ui)
                self.line()

            key, sel = self.menu(top, [a[1] for a in actions], "↑↓ move · ⏎ choose · q back", sel)
            if key == "esc" or actions[sel][0] == "back":
                return
            self.act(p, actions[sel][0])

    def act(self, p: Project, what: str) -> None:
        from . import cli  # the same commands the CLI runs

        ui = self.ui
        if what == "run":
            self.outside(lambda: (cli.show_header(p, ui), self.loop(p, ui, None, None)))
        elif what == "change":
            def change() -> None:
                msg = ui.ask("What should change?")
                if msg:
                    cli.show_header(p, ui)
                    self.loop(p, ui, msg, None)
            self.outside(change)
        elif what == "answer":
            self.outside(lambda: cli.ask_questions(p, ui))
        elif what == "check":
            self.outside(lambda: (cli.show_header(p, ui), cli.do_check(p, ui)))
        elif what == "open":
            self.outside(lambda: cli.open_result(p, ui))
        elif what == "folder":
            opener = {"darwin": ["open"], "win32": ["explorer"]}.get(sys.platform, ["xdg-open"])
            r = proc.run([*opener, str(p.root)], timeout=15)
            if not r.ok and sys.platform != "win32":  # explorer exits 1 even when it worked
                self.outside(lambda: ui.say(f"   {p.root}"))

    def new_project(self) -> Optional[str]:
        """A few questions in the normal screen, then the project is made in the projects folder."""
        result: dict = {}

        def ask() -> bool:
            ui = self.ui
            self.w(CLEAR)
            for row in banner.render(ui.width(), ui.fancy):
                ui.say(row)
            ui.say("")
            ui.say(ui.bold("  New project") + ui.dim(f"  (in {projects_dir()}, empty answer to cancel)"))
            ui.say("")
            request = ui.ask("What do you want to make?")
            if not request:
                return False
            while True:
                raw = ui.ask("Something to recreate? web address, file, folder or command (Enter for none):")
                try:
                    target = parse_target(raw)
                    break
                except CraftError as e:
                    ui.error(e.message)
                    ui.say(f"   {ui.dim(e.fix)}")
            deep = ui.choose("Mode?", ["Clean room: only what a visitor or user sees", "Deep: look inside the original (private use)"]).startswith("Deep")
            allow_run = False
            if target["type"] == "local" and os.access(target["value"], os.X_OK) and Path(target["value"]).is_file():
                allow_run = ui.ask("Run it to record what it prints? [y/N]").lower() in ("y", "yes", "o", "oui")
            folder = projects_dir() / slug(request)
            n = 2
            while folder.exists():
                folder = projects_dir() / f"{slug(request)}-{n}"
                n += 1
            kind = tables.detect_kind(request, target["type"])
            stack = tables.detect_stack(request)["name"]
            p = Project.create(folder, target, request, kind, stack, deep, allow_run)
            ui.step("done", "new", f"{folder}  ·  {kind} · {stack} · {p.mode()}")
            result["path"] = str(folder)
            from . import agent

            if not agent.installed():
                ui.say("")
                ui.warn("No coding agent found yet: building needs one.")
                agent.guide(ui)
                return True
            if ui.choose("Start building now?", ["Yes, start", "Later"]).startswith("Yes"):
                ui.say("")
                from . import cli

                cli.show_header(p, ui)
                self.loop(p, ui, None, None)
                return True
            return False

        self.outside(ask)
        return result.get("path")
