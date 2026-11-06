"""craft: study → build → check → refine, from the terminal.

  craft                           the home screen: past creations, a new project
  craft new [TARGET] [REQUEST…]   start a project (also: craft-new) (asks for what's missing)
  craft run [MESSAGE…]            the whole loop; with a message, a change to the build
  craft study | build | check     one step at a time
  craft status                    where the project is
  craft answer                    answer the builder's questions
  craft brief                     print the builder's brief (to paste into any agent)
  craft open                      open the result
  craft agents                    which coding agents are installed, and how to get one
  craft skill [--install DIR]     print or install the SKILL.md this tool follows
"""

from __future__ import annotations

import argparse
import signal
import sys
import webbrowser
from pathlib import Path
from typing import Optional

from . import __version__, agent, brief, browser, checks, study, tables
from .ui import UI
from .workspace import STEPS, CraftError, Project, parse_target, read_json, slug, write_atomic

STEP_STATE = {"todo": "todo", "running": "run", "done": "done", "failed": "fail", "waiting": "wait", "paused": "wait"}


# --- views ----------------------------------------------------------------------------------------

def show_status(p: Project, ui: UI) -> None:
    s = p.state
    ui.header(s["name"], f"{s['kind']} · {s['stack']} · {p.mode()}")
    ui.say(f"   {ui.dim('“' + s['request'] + '”')}")
    last = read_json(p.round_dir(s.get("round", 0)) / "result.json") if s.get("round") else None
    details = {
        "study": s["target"]["value"] or "no target",
        "build": f"{s.get('agent') or 'agent'} · refinements {s.get('rounds_used', 0)}/{s.get('max_rounds')}",
        "check": (f"round {last['round']}: " + ", ".join(f"{c['id']} {'✓' if c['passed'] else ('–' if c['passed'] is None else '✗')}" + (f" {c['score']:.0f}%" if c.get("score") is not None else "") for c in last["checks"])) if isinstance(last, dict) else "",
        "ready": "",
    }
    for step in STEPS:
        ui.step(STEP_STATE.get(s["steps"].get(step, "todo"), "todo"), step, details[step])
    extra = []
    if p.pending_questions():
        extra.append(f"{len(p.pending_questions())} question(s) waiting: craft answer")
    if p.open_unknowns():
        extra.append(f"{p.open_unknowns()} open unknown(s) in unknowns.md")
    for e in extra:
        ui.say(f"   {ui.yellow('›')} {e}")


def ask_questions(p: Project, ui: UI) -> Optional[list[dict]]:
    """Ask pending questions in the terminal. None when they can't be asked here (not a terminal)."""
    pending = p.pending_questions()
    if not pending:
        return []
    if not ui.interactive():
        return None
    answered = []
    for q in pending:
        choices = [c for c in q.get("choices", []) if isinstance(c, str)][:6]
        a = ui.choose(q["question"], choices) if choices else ui.ask(q["question"])
        if a:
            answered.append({**q, "answer": a})
    p.save_answers(answered)
    p.log("answers: " + "; ".join(f"{q['question']} → {q['answer']}" for q in answered))
    return answered


# --- steps ----------------------------------------------------------------------------------------

def do_study(p: Project, ui: UI) -> None:
    p.set_step("study", "running")
    ui.stage("study", p.state["target"]["value"] or "no target: the request alone")
    study.study(p, ui)
    p.set_step("study", "done")
    if p.state["target"]["type"] != "website":
        ui.step("done", "study", "capture/README.md written")


def write_brief(p: Project) -> str:
    text = brief.first(p)
    write_atomic(p.root / "BRIEF.md", text + "\n")
    return text


def do_check(p: Project, ui: UI, self_check: bool = False) -> dict:
    n = 0 if self_check else p.state.get("round", 0) + 1
    if not self_check:
        p.state["round"] = n
        p.set_step("check", "running")
        ui.stage("check", f"round {n}")
    res = checks.run_checks(p, n, ui)
    checks.show(res, ui)
    if not self_check:
        p.set_step("check", "done" if res["good"] else "failed")
    return res


def finish(p: Project, ui: UI, res: Optional[dict], reply: str) -> None:
    ok = bool(res and res["good"])
    p.set_step("ready", "done" if ok else "failed")
    ui.stage("ready")
    ui.step("done" if ok else "fail", "ready", "every check passes" if ok else "not yet: stopped before every check passed")
    if reply.strip():
        ui.say("")
        for line in reply.strip().splitlines()[-12:]:
            ui.say(f"   {line}")
    ui.say("")
    ui.say(f"   {ui.dim('open it:')} craft open   {ui.dim('change it:')} craft run \"…\"")


def loop(p: Project, ui: UI, message: Optional[str], agent_name: Optional[str]) -> int:
    s = p.state
    agent.resolve(s.get("agent"), agent_name)  # no agent: say how to get one now, not after the study
    if message:  # a new request resets the refinement budget; retries never do
        s["rounds_used"] = 0
        s["unchanged"] = 0
        p.save()
    if s["steps"].get("study") != "done":
        do_study(p, ui)
    else:
        ui.step("done", "study", "evidence in capture/")
    if ask_questions(p, ui) is None:
        p.set_step("build", "waiting")
        ui.step("wait", "build", "the builder asked something: craft answer")
        return 3
    answered = p.undelivered_answers()
    ans = brief.answers_text(answered)
    if message:
        text, label = brief.follow_up(p, message, ans), "changing the build"
    elif s["steps"].get("build") == "todo":
        text, label = write_brief(p) + ans, "building"
    else:
        text, label = brief.resume(p, ans), "carrying on"
    reply, res = "", None
    while True:
        before = p.fingerprint()
        p.set_step("build", "running")
        ui.stage("refine" if label.startswith("refin") else "build", f"{label} · turn {s.get('turns', 0) + 1}")
        try:
            reply = agent.turn(p, text, ui, agent_name, label)
            p.mark_delivered(answered)
        except KeyboardInterrupt:
            p.set_step("build", "paused")
            ui.step("wait", "build", "paused: craft run carries on")
            return 130
        changed = p.fingerprint() != before
        s["unchanged"] = 0 if changed else s.get("unchanged", 0) + 1
        p.set_step("build", "done")
        ui.step("done", "build", reply.strip().splitlines()[-1][:80] if reply.strip() else "turn finished")
        if ask_questions(p, ui) is None:
            p.set_step("build", "waiting")
            ui.step("wait", "build", "the builder asked something: craft answer, then craft run")
            return 3
        answered = p.undelivered_answers()
        res = do_check(p, ui)
        if res["good"]:
            break
        if s["unchanged"] >= tables.UNCHANGED_LIMIT:
            ui.error(f"The builder changed nothing {s['unchanged']} turns in a row; stopping. Add detail with craft run \"…\".")
            break
        if s["rounds_used"] >= s["max_rounds"]:
            ui.error(f"{s['max_rounds']} refinements used for this request. Ask for a change (craft run \"…\") to start a new budget.")
            break
        s["rounds_used"] += 1
        p.save()
        text = brief.refine(p, checks.refine_text(res), brief.answers_text(answered))
        label = f"refining {s['rounds_used']}/{s['max_rounds']}"
    finish(p, ui, res, reply)
    return 0 if res and res["good"] else 1


# --- commands -------------------------------------------------------------------------------------

def cmd_new(a, ui: UI) -> int:
    target_raw = a.target
    request = " ".join(a.request).strip()
    if target_raw and not request and not target_raw.startswith(("http", "/", ".", "~")) and " " in target_raw:
        target_raw, request = "", target_raw  # `craft new "a todo app in rust"`
    if ui.interactive():
        if not request:
            request = ui.ask("What do you want to make?")
        if target_raw is None:
            target_raw = ui.ask("Something to recreate? (web address, path, command — or Enter for none)")
    if not request:
        raise CraftError("A request is needed.", 'craft new [TARGET] "what you want to make"')
    target = parse_target(target_raw or "")
    kind = a.kind or tables.detect_kind(request, target["type"])
    stack = tables.stack_by_name(a.stack)["name"] if a.stack else tables.detect_stack(request)["name"]
    folder = Path(a.dir) if a.dir else Path.cwd() / slug(request)
    p = Project.create(folder.resolve(), target, request, kind, stack, a.deep, a.allow_run)
    ui.header(p.state["name"], f"{kind} · {stack} · {p.mode()}")
    ui.step("done", "new", str(folder))
    ui.say(f"   {ui.dim('add pictures to')} {folder / 'reference'}{ui.dim(', then:')} cd {folder.name} && craft run")
    if not agent.installed():
        ui.say("")
        ui.warn("No coding agent found yet: `craft run` needs one.")
        agent.guide(ui)
    return 0


def cmd_agents(a, ui: UI) -> int:
    table = tables.agents()
    found = agent.installed(table)
    for n in tables.AGENT_ORDER:
        if n not in table:
            continue
        spec = table[n]
        title = spec.get("title", n)
        where = agent.proc.which(spec["argv"][0])
        if where:
            ui.step("done", n, f"{title} · {where}" + ("  ← used by default" if found and n == found[0] else ""), stage="ready")
        else:
            ui.step("todo", n, f"{title} · not installed" + (f": {spec.get('install', 'install ' + spec['argv'][0])}" if found else ""))
    if not found:
        ui.say("")
        ui.warn("No coding agent found.")
        agent.guide(ui)
    else:
        ui.say(f"   {ui.dim('pick another with')} craft run --agent NAME {ui.dim('or')} CRAFT_AGENT=NAME")
    return 0


def cmd_run(a, ui: UI) -> int:
    p = Project.open(Path(a.C))
    show_header(p, ui)
    return loop(p, ui, " ".join(a.message).strip() or None, a.agent)


def show_header(p: Project, ui: UI) -> None:
    ui.header(p.state["name"], f"{p.state['kind']} · {p.state['stack']} · {p.mode()}")


def cmd_study(a, ui: UI) -> int:
    p = Project.open(Path(a.C))
    show_header(p, ui)
    do_study(p, ui)
    return 0


def cmd_build(a, ui: UI) -> int:
    p = Project.open(Path(a.C))
    show_header(p, ui)
    msg = " ".join(a.message).strip()
    first = p.state["steps"].get("build") == "todo"
    text = brief.follow_up(p, msg) if msg else (write_brief(p) if first else brief.resume(p))
    p.set_step("build", "running")
    ui.stage("build", f"turn {p.state.get('turns', 0) + 1}")
    reply = agent.turn(p, text, ui, a.agent, "building")
    p.set_step("build", "done")
    ui.step("done", "build", "turn finished")
    for line in reply.strip().splitlines()[-8:]:
        ui.say(f"   {line}")
    return 0


def cmd_check(a, ui: UI) -> int:
    p = Project.open(Path(a.C))
    if not a.self:
        show_header(p, ui)
    res = do_check(p, ui, self_check=a.self)
    return 0 if res["good"] else 1


def cmd_status(a, ui: UI) -> int:
    show_status(Project.open(Path(a.C)), ui)
    return 0


def cmd_answer(a, ui: UI) -> int:
    p = Project.open(Path(a.C))
    if not p.pending_questions():
        ui.step("done", "answer", "no questions waiting")
        return 0
    if ask_questions(p, ui) is None:
        raise CraftError("Questions need a terminal to answer.", "Edit questions.json and add an \"answer\" to each question.")
    ui.step("done", "answer", "saved; craft run carries on")
    return 0


def cmd_brief(a, ui: UI) -> int:
    p = Project.open(Path(a.C))
    print(write_brief(p))
    return 0


def cmd_open(a, ui: UI) -> int:
    return open_result(Project.open(Path(a.C)), ui)


def open_result(p: Project, ui: UI) -> int:
    site = p.site_dir()
    if site is not None:
        with browser.serve(site) as url:
            ui.step("run", "open", f"{url}  {ui.dim('(Ctrl-C to stop)')}")
            webbrowser.open(url)
            try:
                while True:
                    input()
            except (KeyboardInterrupt, EOFError):
                return 0
    run = p.app_spec().get("run")
    if not run:
        raise CraftError("Nothing to open yet.", 'The build declares how to run it in app/craft-app.json ("run" or "site").')
    ui.step("run", "open", " ".join(run))
    import subprocess  # the person's own interactive run: their terminal, their input

    try:
        return subprocess.call(run, cwd=str(p.app))
    except (OSError, KeyboardInterrupt) as e:
        raise CraftError(f"It couldn't start: {e}", "Check the run command in app/craft-app.json.")


def cmd_home(a, ui: UI) -> int:
    if not ui.interactive():
        raise CraftError("The home screen needs a terminal.", "Use craft new / craft run / craft status instead.")
    from .home import Home

    return Home(ui, loop, show_status).run()


def cmd_skill(a, ui: UI) -> int:
    text = (Path(__file__).parent / "SKILL.md").read_text("utf-8")
    if not a.install:
        print(text)
        return 0
    dest = Path(a.install).expanduser() / "craft" / "SKILL.md"
    write_atomic(dest, text)
    ui.step("done", "skill", str(dest))
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="craft", description="Study → build → check → refine any software, from the terminal.")
    ap.add_argument("-C", default=".", metavar="DIR", help="project folder (default: here)")
    ap.add_argument("--version", action="version", version=f"craft {__version__}")
    sub = ap.add_subparsers(dest="cmd")

    n = sub.add_parser("new", help="start a project")
    n.add_argument("target", nargs="?", help="web address, file, folder or command to recreate")
    n.add_argument("request", nargs="*", help="what you want to make")
    n.add_argument("--kind", choices=list(tables.KINDS))
    n.add_argument("--stack", help="e.g. rust, python, react, html")
    n.add_argument("--deep", action="store_true", help="allow looking inside the original (private use)")
    n.add_argument("--allow-run", action="store_true", help="allow running the original program to record what it prints")
    n.add_argument("--dir", help="project folder (default: a new folder named after the request)")
    n.set_defaults(fn=cmd_new)

    for name, fn, hlp in (("run", cmd_run, "the whole loop (or a change, with a message)"), ("build", cmd_build, "one builder turn")):
        r = sub.add_parser(name, help=hlp)
        r.add_argument("message", nargs="*")
        r.add_argument("--agent", help=f"coding agent: {', '.join(tables.AGENT_ORDER)} (default: first installed)")
        r.set_defaults(fn=fn)

    c = sub.add_parser("check", help="run the checks")
    c.add_argument("--self", action="store_true", help="the builder's own check (round 0, not counted)")
    c.set_defaults(fn=cmd_check)
    for name, fn, hlp in (("study", cmd_study, "gather evidence into capture/"), ("status", cmd_status, "where the project is"),
                          ("answer", cmd_answer, "answer the builder's questions"), ("brief", cmd_brief, "print the builder's brief"),
                          ("open", cmd_open, "open the result")):
        sub.add_parser(name, help=hlp).set_defaults(fn=fn)
    sub.add_parser("home", help="the home screen: past creations and a new project").set_defaults(fn=cmd_home)
    sub.add_parser("agents", help="which coding agents are installed, and how to get one").set_defaults(fn=cmd_agents)
    s = sub.add_parser("skill", help="print or install SKILL.md")
    s.add_argument("--install", metavar="DIR", help="skills folder, e.g. ~/.claude/skills")
    s.set_defaults(fn=cmd_skill)
    return ap


def _stop_on_signal(signum, frame) -> None:
    # A closed terminal (SIGHUP) or a polite kill (SIGTERM) becomes the same stop as Ctrl-C, so the
    # agent and anything else started (each in its own process group) is killed, never orphaned.
    raise KeyboardInterrupt


def main(argv: Optional[list] = None) -> int:
    for name in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            try:
                signal.signal(getattr(signal, name), _stop_on_signal)
            except (ValueError, OSError):  # not the main thread, or not allowed here
                pass
    ui = UI()
    ap = parser()
    a = ap.parse_args(argv)
    if not getattr(a, "fn", None) and ui.interactive():
        a.fn = cmd_home
    if not getattr(a, "fn", None):
        try:
            show_status(Project.open(Path(a.C)), ui)
            return 0
        except CraftError:
            ap.print_help()
            return 0
    try:
        return a.fn(a, ui)
    except CraftError as e:
        ui.report(e)
        return 2
    except KeyboardInterrupt:
        ui.say("")
        ui.say(f"   {ui.dim('stopped')}")
        return 130


def main_new() -> int:
    """`craft-new …` is `craft new …`."""
    return main(["new", *sys.argv[1:]])


def main_run() -> int:
    """`craft-run …` is `craft run …`."""
    return main(["run", *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(main())
