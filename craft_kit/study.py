"""Study: gather evidence about the target into capture/, README.md first.

Clean room (default): only what a visitor or user sees: screenshots and visible facts of a website,
the person's pictures in reference/, and (with --allow-run) what a program prints when run.
Deep: also look inside: a site's HTML, a folder's files and manifests, a program's strings."""

from __future__ import annotations

import json
import os
import shutil
import re
import urllib.request
from collections import Counter
from pathlib import Path

from . import browser, proc, tables
from .ui import UI
from .workspace import IGNORED, Project, write_atomic

RUN_INPUTS: list[list[str]] = [[], ["--help"], ["--version"], ["-h"]]
MANIFESTS = ["package.json", "Cargo.toml", "pyproject.toml", "go.mod", "requirements.txt", "setup.py", "Makefile", "CMakeLists.txt", "README.md", "README", "README.txt"]
PICTURES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def study(p: Project, ui: UI) -> None:
    t = p.state["target"]
    cap = p.capture
    if cap.exists():
        shutil.rmtree(cap, ignore_errors=True)
    cap.mkdir(parents=True, exist_ok=True)
    notes = [
        "# Evidence",
        "",
        f"Request: “{p.state['request']}”",
        f"Target: {t['value'] or 'none (build from the request)'}",
        f"Mode: {p.mode()}" + ("" if p.deep else " — nothing inside the original was read; don't read it either."),
        "",
    ]
    if t["type"] == "website":
        notes.append(_website(p, t["value"], ui))
    elif t["type"] == "local":
        path = Path(t["value"])
        if p.deep:
            notes.append(_inside(path, cap, ui))
        else:
            notes.append("## Clean room\n\nThe program, its files and its folder weren't opened. Build from the request, the pictures in reference/ and what it prints below (if anything). Ask the person about what can't be seen.\n")
        if p.state.get("allow_run") and _runnable(path):
            notes.append(_runs(path, cap, ui))
        elif _runnable(path):
            notes.append("It wasn't run (start the project with --allow-run to record what it prints).\n")
    else:
        notes.append("No target: build from the request alone.\n")
    pics = sorted(x.name for x in p.reference.glob("*") if x.suffix.lower() in PICTURES) if p.reference.exists() else []
    if pics:
        notes.append("## Pictures from the person (reference/)\n\n" + "\n".join(f"- {n}" for n in pics) + "\n\nOpen each one and look closely.\n")
    write_atomic(cap / "README.md", "\n".join(notes))
    p.log(f"study done: {len(list(cap.rglob('*')))} files in capture/")


def _website(p: Project, url: str, ui: UI) -> str:
    out = []
    with ui.live(f"photographing {url}", "study") as live:
        shots, facts, problems = browser.capture(url, p.capture, tables.WIDTHS, facts=True, live=live)
    if facts:
        write_atomic(p.capture / "capture.json", json.dumps({"version": 1, "url": url, "widths": tables.WIDTHS, "facts": facts}, indent=1, ensure_ascii=False))
    out.append("## Screenshots\n")
    out += [f"- {s.name}" for s in shots] or ["None could be taken."]
    out.append("\nOpen every screenshot and match it width by width: layout, spacing, sizes, colours, fonts, what changes on a phone.\n")
    out.append(browser.facts_markdown(facts))
    for prob in problems:
        ui.note(prob)
        out.append(f"> {prob}\n")
    if p.deep:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "craftkit"})
            with urllib.request.urlopen(req, timeout=30) as r:
                html = r.read(2_000_000).decode("utf-8", "replace")
            write_atomic(p.capture / "page.html", html)
            out.append("Deep: the page's HTML as served is in page.html (rebuild what you learn; never paste it into app/).\n")
        except (OSError, ValueError) as e:
            out.append(f"Deep: the page's HTML couldn't be fetched ({e}).\n")
    ui.step("done" if shots else "fail", "study", f"{len(shots)} screenshot(s)" + (", visible facts" if facts else ""))
    return "\n".join(out)


def _runnable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _runs(program: Path, cap: Path, ui: UI) -> str:
    runs = []
    with ui.live(f"running {program.name} with {len(RUN_INPUTS)} inputs", "study") as live:
        for args in RUN_INPUTS:
            live.event("run", f"{program.name} {' '.join(args)}".strip())
            r = proc.run([str(program), *args], cwd=str(cap), timeout=10, cap=16_000)
            runs.append({"args": args, "code": r.code, "output": r.output[-16_000:], "timed_out": r.timed_out, "error": r.error})
    write_atomic(cap / "runs.json", json.dumps({"version": 1, "program": program.name, "runs": runs}, indent=1, ensure_ascii=False))
    lines = ["## What it prints (runs.json)", ""]
    for run in runs:
        first = (run["output"].strip().splitlines() or [run["error"] or "(nothing)"])[0][:100]
        lines.append(f"- `{program.name} {' '.join(run['args'])}`: exit {run['code']} — {first}")
    lines.append("\nThe rebuild must print the same for each input and exit the same way; the check reruns these inputs.\n")
    ui.step("done", "runs", f"{len(runs)} runs recorded")
    return "\n".join(lines)


def _inside(path: Path, cap: Path, ui: UI) -> str:
    out = ["## Deep: what's inside", ""]
    if path.is_dir():
        exts: Counter = Counter()
        files = size = 0
        top = sorted(x.name + ("/" if x.is_dir() else "") for x in path.iterdir())[:80]
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if d not in IGNORED]
            for n in filenames:
                files += 1
                exts[Path(n).suffix.lower() or "(none)"] += 1
                try:
                    size += (Path(dirpath) / n).stat().st_size
                except OSError:
                    pass
            if files > 50_000:
                break
        out.append(f"{files} files, {size / 1e6:.1f} MB. Top level: " + ", ".join(top))
        out.append("\nBy type: " + ", ".join(f"{e} {c}" for e, c in exts.most_common(15)))
        man = cap / "manifests"
        copied = []
        for name in MANIFESTS:
            src = path / name
            if src.is_file() and src.stat().st_size < 200_000:
                man.mkdir(exist_ok=True)
                shutil.copyfile(src, man / name)
                copied.append(name)
        if copied:
            out.append("\nCopied to capture/manifests/: " + ", ".join(copied) + " (read them first).")
        stacks = [tc["file"] for tc in tables.TOOLCHAINS if (path / tc["file"]).exists()]
        if stacks:
            out.append(f"Built with: {', '.join(stacks)}.")
        out.append(f"\nThe original folder is {path}: read what you need there, never change it.\n")
    elif path.is_file():
        st = path.stat()
        out.append(f"{path.name}: {st.st_size / 1e6:.2f} MB.")
        if proc.which("file"):
            r = proc.run(["file", "-b", str(path)], timeout=20)
            if r.ok:
                out.append(f"Type: {r.output.strip()}")
        found = _strings(path)
        write_atomic(cap / "strings.txt", "\n".join(found))
        out.append(f"\n{len(found)} readable strings saved to strings.txt (options, messages, names: clues to its features).\n")
    ui.step("done", "inside", "inventory written")
    return "\n".join(out)


def _strings(path: Path, minimum: int = 6, limit: int = 3000, scan: int = 32_000_000) -> list[str]:
    try:
        with open(path, "rb") as f:
            data = f.read(scan)
    except OSError:
        return []
    found: list[str] = []
    seen: set = set()
    for m in re.finditer(rb"[\x20-\x7e\t]{%d,}" % minimum, data):
        s = m.group().decode("ascii").strip()
        if s and s not in seen:
            seen.add(s)
            found.append(s[:200])
            if len(found) >= limit:
                break
    return found
