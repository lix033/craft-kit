"""One builder turn: hand a message to a coding-agent CLI on stdin, show what it does on one live
line, and return its final reply."""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

from . import proc, tables
from .ui import UI
from .workspace import CraftError, Project, write_atomic

TURN_TIMEOUT = float(os.environ.get("CRAFT_TURN_TIMEOUT", 3 * 3600))
IDLE_TIMEOUT = float(os.environ.get("CRAFT_IDLE_TIMEOUT", 20 * 60))


def installed(table: Optional[dict] = None) -> list[str]:
    """The agents whose program is on this computer, in order of preference."""
    table = table or tables.agents()
    return [n for n in tables.AGENT_ORDER if n in table and proc.which(table[n]["argv"][0])]


def guide(ui: UI, names: Optional[list] = None) -> None:
    """How to install and sign in to a coding agent, with the exact commands."""
    table = tables.agents()
    names = [n for n in (names or tables.AGENT_ORDER) if n in table]
    platform = sys.platform if sys.platform in ("darwin", "win32") else "linux"
    ui.say("")
    ui.say(f"   craft doesn't write code itself: a coding agent does. {'Install it' if len(names) == 1 else 'Install one of these'}, then sign in once:")
    ui.say("")
    width = max([len(table[n].get("title", n)) for n in names] + [8]) + 3
    for n in names:
        spec = table[n]
        title = spec.get("title", n)
        install = spec.get("install") or f"install `{spec['argv'][0]}` and put it on your PATH"
        ui.say(f"   {ui.bold(f'{title:<{width}}')}{install}")
        alt = (spec.get("alt") or {}).get(platform)
        if alt:
            ui.say(f"   {' ' * width}{ui.dim('or:')} {alt}")
        if spec.get("login"):
            ui.say(f"   {' ' * width}{ui.dim('then ' + spec['login'])}")
    if not proc.which("npm"):
        ui.say("")
        ui.say(f"   {ui.yellow('npm')} isn't on this computer: it comes with Node.js ({tables.NODE_URL}).")
    ui.say("")
    ui.say(f"   {ui.dim('Then:')} craft run   {ui.dim('· see what is found:')} craft agents")
    ui.say(f"   {ui.dim('No agent here? craft brief prints the task: paste it into any coding assistant')}")
    ui.say(f"   {ui.dim('(Cursor, Copilot, …) opened in the project folder, then run')} craft check{ui.dim('.')}")


def no_agent() -> CraftError:
    return CraftError("No coding agent found on this computer (Claude Code, Codex or Gemini CLI).", guide=guide)


def resolve(remembered: Optional[str], asked: Optional[str]) -> tuple[str, dict, Optional[str]]:
    """The agent for a project: (name, spec, the remembered agent that's gone, if any). Raises a
    CraftError with install steps when none can run."""
    if not asked and not os.environ.get("CRAFT_AGENT") and remembered and remembered not in installed():
        name, spec = pick(None)
        return name, spec, remembered
    name, spec = pick(asked or remembered)
    return name, spec, None


def pick(name: Optional[str], strict: bool = True) -> tuple[str, dict]:
    """The agent to use. An agent asked for by name must be installed; one only remembered from an
    earlier run gives way to another installed agent."""
    table = tables.agents()
    explicit = name or os.environ.get("CRAFT_AGENT")
    if explicit:
        if explicit == "none":
            raise CraftError("No agent: the brief is in BRIEF.md.", "Paste BRIEF.md into any coding agent opened in this folder, then run `craft check`.")
        if explicit not in table:
            raise CraftError(f"Unknown agent “{explicit}”.", f"Known: {', '.join(table)}. Add one in {tables.config_dir() / 'agents.json'}.")
        if proc.which(table[explicit]["argv"][0]) or not strict:
            return explicit, table[explicit]
        title = table[explicit].get("title", explicit)
        others = [n for n in installed(table) if n != explicit]
        hint = f" ({', '.join(others)} is installed: craft run --agent {others[0]})" if others else ""
        raise CraftError(f"{title} isn't installed, or isn't on your PATH{hint}.", guide=lambda ui: guide(ui, [explicit]))
    found = installed(table)
    if found:
        return found[0], table[found[0]]
    raise no_agent()


TOOL_KINDS = {
    "Read": "read", "NotebookRead": "read", "LS": "read",
    "Edit": "edit", "MultiEdit": "edit", "NotebookEdit": "edit",
    "Write": "write",
    "Bash": "run", "BashOutput": "run", "KillShell": "run",
    "Grep": "search", "Glob": "search",
    "WebFetch": "web", "WebSearch": "web",
    "TodoWrite": "plan", "Task": "agent", "Agent": "agent",
}


class _Claude:
    """Reads Claude Code's stream-json: every action for the live feed, the final reply and session id."""

    def __init__(self, live, root: str = ""):
        self.live = live
        self.root = root.rstrip("/") + "/" if root else ""
        self.reply = ""
        self.session: Optional[str] = None
        self.is_error = False
        self._started = False

    def __call__(self, line: str) -> None:
        try:
            ev = json.loads(line)
        except ValueError:
            return
        if not isinstance(ev, dict):
            return
        if ev.get("session_id"):
            self.session = ev["session_id"]
        kind = ev.get("type")
        if kind == "system" and ev.get("subtype") == "init" and not self._started:
            self._started = True
            model = ev.get("model")
            self.live.event("agent", f"session started{f' · {model}' if isinstance(model, str) else ''}", count=False)
        elif kind == "assistant":
            for item in (ev.get("message") or {}).get("content") or []:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "tool_use":
                    name = str(item.get("name", ""))
                    self.live.event(_tool_kind(name), _describe_tool(name, item.get("input") or {}, self.root))
                elif item.get("type") == "text" and isinstance(item.get("text"), str):
                    first = next((ln for ln in item["text"].strip().splitlines() if ln.strip()), "")
                    self.live.event("say", first)
        elif kind == "user":
            for item in (ev.get("message") or {}).get("content") or []:
                if isinstance(item, dict) and item.get("type") == "tool_result" and item.get("is_error"):
                    self.live.event("fail", _first_line(item.get("content")) or "a tool call failed")
        elif kind == "result":
            self.reply = str(ev.get("result") or "")
            self.is_error = bool(ev.get("is_error"))


def _tool_kind(name: str) -> str:
    return TOOL_KINDS.get(name, "tool")


def _first_line(content) -> str:
    if isinstance(content, list):
        content = " ".join(c.get("text", "") for c in content if isinstance(c, dict) and isinstance(c.get("text"), str))
    if not isinstance(content, str):
        return ""
    return next((ln.strip() for ln in content.splitlines() if ln.strip()), "")


def _describe_tool(name: str, args: dict, root: str = "") -> str:
    def rel(v: str) -> str:
        return v[len(root):] if root and v.startswith(root) else v

    if name == "TodoWrite" and isinstance(args.get("todos"), list):
        todos = [t for t in args["todos"] if isinstance(t, dict)]
        done = sum(1 for t in todos if t.get("status") == "completed")
        active = [t.get("activeForm") or t.get("content") for t in todos if t.get("status") == "in_progress"]
        now = active[0] if active and isinstance(active[0], str) else ("all done" if todos and done == len(todos) else "updating the plan")
        return f"{done}/{len(todos)} · {now}" if todos else now
    if name in ("Task", "Agent") and isinstance(args.get("description"), str):
        return args["description"]
    if name in ("Grep", "Glob") and isinstance(args.get("pattern"), str):
        where = rel(args["path"]) if isinstance(args.get("path"), str) else ""
        return args["pattern"] + (f"  in {where}" if where else "")
    if name == "Bash" and isinstance(args.get("command"), str):
        return args["command"].strip().splitlines()[0] if args["command"].strip() else "(empty command)"
    for key in ("file_path", "notebook_path", "path", "pattern", "url", "query", "command"):
        if isinstance(args.get(key), str):
            text = rel(args[key])
            return text if name in TOOL_KINDS else f"{name.split('__')[-1]} {text}"
    return name.split("__")[-1] or name


def turn(p: Project, message: str, ui: UI, agent: Optional[str], label: str) -> str:
    name, spec, gone = resolve(p.state.get("agent"), agent)
    if gone:
        ui.note(f"{gone} isn't on this computer any more; using {name}.")
        p.state["session"] = None
    p.state["agent"] = name
    p.state["turns"] = p.state.get("turns", 0) + 1
    rd = p.root / "checks" / f"turn-{p.state['turns']}"
    rd.mkdir(parents=True, exist_ok=True)
    write_atomic(rd / "message.md", message)
    p.log(f"turn ({name}): {label}")
    for attempt in (1, 2):
        argv = list(spec["argv"])
        session = p.state.get("session")
        if session and spec.get("resume"):
            argv += [a.replace("{session}", session) for a in spec["resume"]]
        stage = "refine" if label.startswith("refin") else "build"
        with ui.live(f"{label} · {name}", stage) as live:
            reader = _Claude(live, str(p.root)) if spec.get("stream") == "claude-json" else None

            def on_line(line: str) -> None:
                if reader is not None:
                    reader(line)
                elif line.strip():
                    live.event("out", line.strip())

            r = proc.run(argv, cwd=str(p.root), timeout=TURN_TIMEOUT, idle=IDLE_TIMEOUT, input_text=message, on_line=on_line)
        ui.say(f"   {ui.dim('└ ' + live.tally())}")
        write_atomic(rd / "agent.log", r.output)
        lost = spec.get("lost")
        if attempt == 1 and session and lost and lost in r.output:
            ui.note("The agent's saved conversation isn't on this computer; starting a fresh one.")
            p.state["session"] = None
            p.save()
            continue  # the next message points it at BRIEF.md anyway
        break
    if reader is not None and reader.session:
        p.state["session"] = reader.session
    p.save()
    if not r.ok or (reader is not None and reader.is_error):
        why = r.error or (f"exit {r.code}" if r.code else "it reported an error")
        login = f"If it needs signing in: {spec['login']}.\n" if spec.get("login") else ""
        raise CraftError(f"{name} stopped: {why}.\n{r.tail(12)}", f"{login}Full output: {rd / 'agent.log'}. Fix the cause, then `craft run` carries on.")
    reply = reader.reply if reader is not None else r.tail(40)
    write_atomic(rd / "reply.md", reply)
    return reply
