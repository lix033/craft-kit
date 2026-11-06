"""The project folder and its one state file, craft.json (versioned, written atomically).

<project>/
  craft.json        request, target, kind, stack, mode, rounds used, step states
  BRIEF.md          what the builder is told (regenerated before each first turn)
  capture/          Study's evidence, README.md first (read-only for the builder)
  reference/        pictures or files the person adds (read-only)
  app/              the only folder the builder changes
  checks/round-N/   each check: result.json, screenshots, logs
  checks/turn-N/    each builder turn: the message sent, its log and reply
  unknowns.md       open questions about the original, kept by the builder
  questions.json    questions the builder asks the person, with their answers
  feed.log          everything that happened, in order
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Optional

from . import proc, tables

STATE = "craft.json"
VERSION = 1
STEPS = ["study", "build", "check", "ready"]
IGNORED = {"node_modules", "target", "dist", "out", "build", ".git", "__pycache__", ".venv", "venv", ".next", "shots", ".pytest_cache"}


class CraftError(Exception):
    """A failure with a plain-English remediation."""

    def __init__(self, message: str, fix: str = "", guide=None):
        super().__init__(message)
        self.message = message
        self.fix = fix
        self.guide = guide  # optional callable(ui): a longer, formatted remediation


def write_atomic(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        for attempt in range(5):  # Windows: a scanner may hold the file for a moment
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return default


def parse_target(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        return {"type": "none", "value": ""}
    if re.match(r"^https?://", raw, re.I):
        return {"type": "website", "value": raw}
    p = Path(raw).expanduser()
    if p.exists():
        return {"type": "local", "value": str(p.resolve())}
    found = proc.which(raw)
    if found and os.sep not in raw:
        return {"type": "local", "value": found}
    if re.match(r"^[\w-]+(\.[\w-]+)+(/.*)?$", raw):
        return {"type": "website", "value": f"https://{raw}"}
    raise CraftError(f"Can't find the target “{raw}”.", "Give a web address (https://…), a file or folder path, a command on your PATH, or nothing to build from the request alone.")


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:40].rstrip("-") or "project")


# The projects the person has made or opened, for the home screen (config_dir/projects.json).
REGISTRY_LIMIT = 300


def projects_dir() -> Path:
    """Where the home screen creates new projects."""
    return Path(os.environ.get("CRAFT_PROJECTS_DIR") or Path.home() / "craft-projects").expanduser()


def _registry_path() -> Path:
    return tables.config_dir() / "projects.json"


def remembered() -> list[dict]:
    data = read_json(_registry_path(), {})
    items = data.get("projects") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    good = [i for i in items if isinstance(i, dict) and isinstance(i.get("path"), str)]
    return sorted(good, key=lambda i: str(i.get("opened", "")), reverse=True)


def _save_registry(items: list[dict]) -> None:
    try:
        write_atomic(_registry_path(), json.dumps({"version": 1, "projects": items[:REGISTRY_LIMIT]}, indent=1, ensure_ascii=False) + "\n")
    except OSError:
        pass  # the list is a convenience: never fail a command over it


def remember(root: Path) -> None:
    path = str(Path(root).resolve())
    items = [i for i in remembered() if i["path"] != path]
    items.insert(0, {"path": path, "opened": time.strftime("%Y-%m-%dT%H:%M:%S")})
    _save_registry(items)


def forget(path: str) -> None:
    _save_registry([i for i in remembered() if i["path"] != path])


def find_root(start: Path) -> Path:
    here = start.resolve()
    for d in [here, *here.parents]:
        if (d / STATE).is_file():
            return d
    raise CraftError("This folder isn't a craft project.", "Run `craft new` to start one, or `craft -C <project> …`.")


class Project:
    def __init__(self, root: Path, state: dict):
        self.root = root
        self.state = state

    # paths -------------------------------------------------------------------
    @property
    def app(self) -> Path:
        return self.root / "app"

    @property
    def capture(self) -> Path:
        return self.root / "capture"

    @property
    def reference(self) -> Path:
        return self.root / "reference"

    def round_dir(self, n: int) -> Path:
        return self.root / "checks" / f"round-{n}"

    # state -------------------------------------------------------------------
    @classmethod
    def create(cls, folder: Path, target: dict, request: str, kind: str, stack: str, deep: bool, allow_run: bool) -> "Project":
        if (folder / STATE).exists():
            raise CraftError(f"{folder} is already a craft project.", "Use `craft run` there, or pick another folder with --dir.")
        state = {
            "version": VERSION,
            "name": folder.name,
            "request": request,
            "target": target,
            "kind": kind,
            "stack": stack,
            "deep": deep,
            "allow_run": allow_run,
            "max_rounds": tables.MAX_ROUNDS,
            "good_enough": tables.GOOD_ENOUGH,
            "rounds_used": 0,
            "round": 0,
            "steps": {s: "todo" for s in STEPS},
            "agent": None,
            "session": None,
            "unchanged": 0,
            "fingerprint": None,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        for d in ("app", "capture", "reference", "checks"):
            (folder / d).mkdir(parents=True, exist_ok=True)
        p = cls(folder, state)
        unknowns = folder / "unknowns.md"
        if not unknowns.exists():
            write_atomic(unknowns, "# Unknowns\n\nQuestions the evidence doesn't answer yet.\n`- [ ] question — what would settle it — impact: high|medium|low`; tick with the answer and its evidence.\n\n")
        p.save()
        remember(folder)
        p.log(f"new project: {request!r} target={target['value'] or '-'} kind={kind} stack={stack} mode={'deep' if deep else 'clean room'}")
        return p

    @classmethod
    def open(cls, start: Path) -> "Project":
        root = find_root(start)
        state = read_json(root / STATE)
        if not isinstance(state, dict):
            raise CraftError(f"{root / STATE} can't be read.", "Fix or delete the file; it is JSON.")
        v = state.get("version")
        if not isinstance(v, int) or v > VERSION:
            raise CraftError(f"{STATE} says version {v}; this craft reads version {VERSION}.", "Update craft (`pipx upgrade craftkit`, `uv tool upgrade craftkit` or `npm update -g craftkit-cli`).")
        # migrations go here as versions are added
        state.setdefault("steps", {s: "todo" for s in STEPS})
        remember(root)
        return cls(root, state)

    def save(self) -> None:
        write_atomic(self.root / STATE, json.dumps(self.state, indent=2, ensure_ascii=False) + "\n")

    def set_step(self, step: str, status: str) -> None:
        self.state["steps"][step] = status
        self.save()

    def log(self, text: str) -> None:
        try:
            with open(self.root / "feed.log", "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')} {text}\n")
        except OSError:
            pass

    @property
    def deep(self) -> bool:
        return bool(self.state.get("deep"))

    def mode(self) -> str:
        return "deep" if self.deep else "clean room"

    # what the builder made -----------------------------------------------------
    def app_spec(self) -> dict:
        """How the build is built, tested and run: app/craft-app.json if the builder wrote one,
        else what its files show. Lists of program + arguments; `site` is the folder to serve."""
        spec: dict = {}
        declared = read_json(self.app / "craft-app.json", {})
        if isinstance(declared, dict):
            for key in ("install", "build", "test", "run"):
                v = declared.get(key)
                if isinstance(v, list) and v and all(isinstance(a, str) for a in v):
                    spec[key] = v
            if isinstance(declared.get("site"), str):
                spec["site"] = declared["site"]
        for tc in tables.TOOLCHAINS:
            if (self.app / tc["file"]).exists():
                for key in ("install", "build", "test"):
                    if key not in spec and key in tc:
                        spec[key] = list(tc[key])
                spec.setdefault("toolchain", tc["file"])
                break
        return spec

    def site_dir(self) -> Optional[Path]:
        spec = self.app_spec()
        names = [spec["site"]] if "site" in spec else tables.SITE_DIRS
        for n in names:
            d = (self.app / n).resolve()
            if self.app.resolve() in [d, *d.parents] and (d / "index.html").is_file():
                return d
        return None

    def fingerprint(self) -> str:
        h = hashlib.sha256()
        count = 0
        for dirpath, dirnames, filenames in os.walk(self.app):
            dirnames[:] = sorted(d for d in dirnames if d not in IGNORED)
            for name in sorted(filenames):
                path = Path(dirpath) / name
                try:
                    st = path.stat()
                    h.update(str(path.relative_to(self.app)).encode())
                    if st.st_size <= 1_000_000:
                        h.update(path.read_bytes())
                    else:
                        h.update(f"{st.st_size}:{st.st_mtime_ns}".encode())
                except OSError:
                    continue
                count += 1
                if count > 20_000:
                    return h.hexdigest()
        return h.hexdigest()

    # questions -----------------------------------------------------------------
    def questions(self) -> list[dict]:
        data = read_json(self.root / "questions.json", {})
        qs = data.get("questions") if isinstance(data, dict) else None
        return [q for q in qs if isinstance(q, dict) and isinstance(q.get("question"), str)] if isinstance(qs, list) else []

    def pending_questions(self) -> list[dict]:
        return [q for q in self.questions() if not q.get("answer")]

    def undelivered_answers(self) -> list[dict]:
        """Answers the builder hasn't been given yet (typed here or written into questions.json)."""
        return [q for q in self.questions() if q.get("answer") and not q.get("delivered")]

    def mark_delivered(self, answered: list[dict]) -> None:
        if not answered:
            return
        done = {q["question"] for q in answered}
        qs = self.questions()
        for q in qs:
            if q["question"] in done:
                q["delivered"] = True
        write_atomic(self.root / "questions.json", json.dumps({"version": 1, "questions": qs}, indent=2, ensure_ascii=False) + "\n")

    def save_answers(self, answered: list[dict]) -> None:
        by_q = {q["question"]: q.get("answer") for q in answered}
        qs = self.questions()
        for q in qs:
            if q["question"] in by_q and by_q[q["question"]]:
                q["answer"] = by_q[q["question"]]
        write_atomic(self.root / "questions.json", json.dumps({"version": 1, "questions": qs}, indent=2, ensure_ascii=False) + "\n")

    def open_unknowns(self) -> int:
        try:
            return sum(1 for line in (self.root / "unknowns.md").read_text("utf-8").splitlines() if line.lstrip().startswith("- [ ]"))
        except OSError:
            return 0
