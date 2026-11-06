"""Catalogues as data: kinds of thing made, stacks, toolchains and coding agents.
Override or extend agents with ~/.config/craft/agents.json (same shape as AGENTS)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WIDTHS = [1440, 768, 390]  # desktop, tablet, phone: Study and Check photograph the same widths
MAX_ROUNDS = 6  # refinement rounds per request (kept across runs; a new request resets it)
GOOD_ENOUGH = 90.0  # stop refining once every scored check is at least this alike (percent)
UNCHANGED_LIMIT = 2  # stop when the builder changes nothing this many turns in a row
PLAYWRIGHT = "playwright@1.48.2"

# A kind: how it's recognised (whole words, English and French), what the goal is, which checks judge it.
KINDS: dict[str, dict] = {
    "website": {
        "words": ["website", "site", "webpage", "landing", "homepage", "page", "web"],
        "goal": "a website that looks and behaves like the original at every screen width",
        "checks": ["build", "web", "tests"],
    },
    "game": {
        "words": ["game", "jeu", "gameplay", "arcade", "platformer", "puzzle"],
        "goal": "a playable game with the same rules, controls, numbers and feel",
        "checks": ["build", "selftest", "screenshot"],
    },
    "cli": {
        "words": ["cli", "command", "commande", "console", "terminal", "shell", "script"],
        "goal": "a command-line program that prints the same output and exits with the same codes",
        "checks": ["build", "runs", "tests"],
    },
    "app": {
        "words": ["app", "application", "desktop", "gui", "window", "fenêtre", "mobile"],
        "goal": "an application with the same core features and screens",
        "checks": ["build", "screenshot", "tests"],
    },
    "tool": {
        "words": ["library", "librairie", "bibliothèque", "api", "server", "serveur", "service", "sdk", "package", "plugin", "outil", "tool"],
        "goal": "software that does what the original does, verified by its own tests",
        "checks": ["build", "tests"],
    },
}
KIND_ORDER = ["game", "website", "cli", "app", "tool"]

# A stack: phrases that ask for it (matched on " lower-case words "), and what the builder is told.
STACKS: list[dict] = [
    {"name": "Next.js (static export)", "asked_by": [" next js ", " nextjs "],
     "steps": "Next.js App Router + TypeScript with output: 'export', trailingSlash: true and unoptimized images; build with `npm install && npm run build`; the site is app/out."},
    {"name": "React + TypeScript (Vite)", "asked_by": [" react ", " vite "],
     "steps": "Vite + React + TypeScript with base './'; build with `npm install && npm run build`; the site is app/dist."},
    {"name": "Plain HTML and CSS", "asked_by": [" html ", " plain html ", " no framework ", " sans framework ", " static "],
     "steps": "plain HTML and CSS (JavaScript only where needed), no build step; index.html at the top of app/, one file per page."},
    {"name": "Electron", "asked_by": [" electron "],
     "steps": "Electron + TypeScript or JavaScript, contextIsolation on, nodeIntegration off, IPC through a preload script; a `build` script that exits without opening a window."},
    {"name": "Python", "asked_by": [" python ", " py "],
     "steps": "Python 3.9+ with a pyproject.toml, standard library first; tests with pytest under app/tests."},
    {"name": "Rust", "asked_by": [" rust ", " cargo "],
     "steps": "a cargo project at app/ itself (app/Cargo.toml, app/src/); `cargo build` must succeed and `cargo test` must pass."},
    {"name": "Go", "asked_by": [" go ", " golang "],
     "steps": "a Go module at app/ itself; `go build ./...` must succeed and `go test ./...` must pass."},
    {"name": "Node.js + TypeScript", "asked_by": [" node ", " nodejs ", " typescript ", " javascript ", " js ", " ts "],
     "steps": "Node.js 18+ with TypeScript, a package.json `build` script and tests runnable with `npm test`."},
]
BUILDERS_CHOICE = {
    "name": "Builder's choice",
    "steps": "whatever their request names; otherwise choose the stack that best fits the request and what the original visibly uses, and prefer the simplest one that does the job. A website must build to static files (index.html at the top of a folder) that work when served as they are.",
}

# How a project builds and tests itself, found by the file that names the tool (first match wins).
PY = os.path.basename(sys.executable) if sys.executable else "python3"
TOOLCHAINS: list[dict] = [
    {"file": "package.json", "install": ["npm", "install"], "build": ["npm", "run", "build", "--if-present"], "test": ["npm", "test", "--if-present"]},
    {"file": "Cargo.toml", "build": ["cargo", "build"], "test": ["cargo", "test"]},
    {"file": "go.mod", "build": ["go", "build", "./..."], "test": ["go", "test", "./..."]},
    {"file": "pyproject.toml", "build": [PY, "-m", "compileall", "-q", "."], "test": [PY, "-m", "pytest", "-q"]},
    {"file": "requirements.txt", "build": [PY, "-m", "compileall", "-q", "."], "test": [PY, "-m", "pytest", "-q"]},
    {"file": "CMakeLists.txt", "build": ["cmake", "-S", ".", "-B", "build"], "test": ["ctest", "--test-dir", "build"]},
    {"file": "Makefile", "build": ["make"], "test": ["make", "test"]},
]
NO_TESTS = ["no tests ran", "no tests found", "0 tests", "running 0 tests", "no test files", "missing script: \"test\"", "no tests to run", "collected 0 items"]
SITE_DIRS = ["dist", "out", "build", "public", "."]

# Coding agents, driven headless. The brief goes in on stdin (never argv: it can be long).
_CLAUDE_TOOLS = ",".join(
    ["Read", "Write", "Edit", "Glob", "Grep", "TodoWrite"]
    + [f"Bash({p}:*)" for p in ["npm", "npx", "node", "pnpm", "yarn", "cargo", "rustc", "go", "python", "python3", "pip", "pytest", "make", "cmake", "craft", "ls", "mkdir", "cat"]]
)
AGENTS: dict[str, dict] = {
    "claude": {
        "argv": ["claude", "-p", "--output-format", "stream-json", "--verbose", "--permission-mode", "acceptEdits", "--allowedTools", _CLAUDE_TOOLS],
        "stream": "claude-json",
        "resume": ["--resume", "{session}"],
        "lost": "No conversation found",
        "title": "Claude Code",
        "install": "npm install -g @anthropic-ai/claude-code",
        "alt": {"darwin": "curl -fsSL https://claude.ai/install.sh | bash", "linux": "curl -fsSL https://claude.ai/install.sh | bash", "win32": "irm https://claude.ai/install.ps1 | iex   (PowerShell)"},
        "login": "run `claude` once and sign in (Claude account or API key)",
    },
    "codex": {
        "argv": ["codex", "exec", "--full-auto", "-"],
        "stream": "text",
        "title": "Codex",
        "install": "npm install -g @openai/codex",
        "login": "run `codex` once and sign in (ChatGPT account or API key)",
    },
    "gemini": {
        "argv": ["gemini", "--yolo"],
        "stream": "text",
        "title": "Gemini CLI",
        "install": "npm install -g @google/gemini-cli",
        "alt": {"darwin": "brew install gemini-cli"},
        "login": "run `gemini` once and sign in (a Google account has a free tier)",
    },
}
NODE_URL = "https://nodejs.org"  # npm, used by the install commands above, comes with Node.js
AGENT_ORDER = ["claude", "codex", "gemini"]


def config_dir() -> Path:
    if os.environ.get("CRAFT_CONFIG_DIR"):
        return Path(os.environ["CRAFT_CONFIG_DIR"])
    if os.environ.get("XDG_CONFIG_HOME"):
        return Path(os.environ["XDG_CONFIG_HOME"]) / "craft"
    return Path.home() / ".config" / "craft"


def agents() -> dict[str, dict]:
    table = {k: dict(v) for k, v in AGENTS.items()}
    path = config_dir() / "agents.json"
    try:
        extra = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return table
    if isinstance(extra, dict):
        for name, spec in extra.items():
            if isinstance(spec, dict) and isinstance(spec.get("argv"), list) and all(isinstance(a, str) for a in spec["argv"]):
                table[name] = {**table.get(name, {}), **spec}
                if name not in AGENT_ORDER:
                    AGENT_ORDER.append(name)
    return table


def words(text: str) -> str:
    """Lower-case words padded with spaces, punctuation as spaces: "Next.js," -> " next js "."""
    cleaned = "".join(ch if ch.isalnum() else " " for ch in text.lower())
    return f" {' '.join(cleaned.split())} "


def detect_kind(request: str, target_type: str) -> str:
    w = words(request)
    for kind in KIND_ORDER:
        if any(f" {word} " in w for word in KINDS[kind]["words"]):
            # "site" alone in a request about a game or CLI shouldn't win; KIND_ORDER puts game first.
            return kind
    return "website" if target_type == "website" else "tool"


def detect_stack(request: str) -> dict:
    w = words(request)
    for s in STACKS:
        if any(p in w for p in s["asked_by"]):
            return s
    return BUILDERS_CHOICE


def stack_by_name(name: str) -> dict:
    for s in STACKS:
        if s["name"].lower() == name.lower() or name.lower() in words(s["name"]):
            return s
    return BUILDERS_CHOICE if name.lower() in ("", "builder's choice", "auto", "choice") else {"name": name, "steps": f"{name}, as the request asks."}
