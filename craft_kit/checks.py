"""Check: judge the build against the original, the same way every time, and say what differs.

Each check returns {"id", "passed": True|False|None (couldn't judge), "score": percent|None,
"summary", "claims": [[text, ok, detail]]}. A round is good when no check failed and every score
reaches the project's good_enough."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Optional

from . import browser, png, proc, tables
from .ui import UI
from .workspace import Project, read_json, write_atomic

BUILD_TIMEOUT = 20 * 60
ALIKE = 80.0  # a run's output counts as the same when this many of its words match


def result(cid: str, passed: Optional[bool], summary: str, score: Optional[float] = None, claims: Optional[list] = None) -> dict:
    return {"id": cid, "passed": passed, "score": None if score is None else round(score, 1), "summary": summary, "claims": claims or []}


def check_build(p: Project, rd: Path, live) -> dict:
    spec = p.app_spec()
    if not any(p.app.iterdir()):
        return result("build", False, "app/ is empty: nothing has been built yet.")
    if "install" in spec and not (p.app / "node_modules").exists():
        live.event("run", "installing dependencies: " + " ".join(spec["install"]))
        r = proc.run(spec["install"], cwd=str(p.app), timeout=BUILD_TIMEOUT, idle=600, on_line=live.update)
        if not r.ok:
            return result("build", False, f"Installing dependencies failed ({r.error or f'exit {r.code}'}):\n{r.tail(25)}")
    if "build" not in spec:
        return result("build", True, "Nothing to build (no build command declared or found).")
    live.event("run", " ".join(spec["build"]))
    r = proc.run(spec["build"], cwd=str(p.app), timeout=BUILD_TIMEOUT, idle=600, on_line=live.update)
    write_atomic(rd / "build.log", r.output)
    if r.ok:
        return result("build", True, f"`{' '.join(spec['build'])}` succeeds.")
    return result("build", False, f"`{' '.join(spec['build'])}` fails ({r.error or f'exit {r.code}'}):\n{r.tail(30)}")


def check_tests(p: Project, rd: Path, live) -> dict:
    spec = p.app_spec()
    if "test" not in spec:
        return result("tests", None, "No tests declared or found.")
    live.event("run", " ".join(spec["test"]))
    r = proc.run(spec["test"], cwd=str(p.app), timeout=BUILD_TIMEOUT, idle=600, on_line=live.update)
    write_atomic(rd / "tests.log", r.output)
    low = r.output.lower()
    if any(s in low for s in tables.NO_TESTS):
        return result("tests", None, "The project has no tests yet.")
    if r.ok:
        return result("tests", True, "The tests pass.")
    return result("tests", False, f"The tests fail ({r.error or f'exit {r.code}'}):\n{r.tail(30)}")


def check_web(p: Project, rd: Path, live) -> dict:
    site = p.site_dir()
    if site is None:
        return result("web", False, "No built site found: there must be an index.html in app/dist, app/out, app/build, app/public or app/ (or the folder named by `site` in app/craft-app.json).")
    with browser.serve(site) as url:
        live.event("web", f"photographing the build at {url}")
        shots, _facts, problems = browser.capture(url, rd, tables.WIDTHS, facts=False, live=live)
    if not shots:
        return result("web", None, "The build couldn't be photographed: " + "; ".join(problems))
    claims, scores = [], []
    for shot in shots:
        mine = png.grid(shot)
        if mine is None or mine.blank():
            claims.append([f"At {shot.stem.split('-')[-1]} px, the page shows something", False, "the screenshot is blank"])
            scores.append(0.0)
            continue
        original = p.capture / shot.name
        theirs = png.grid(original) if original.is_file() else None
        if theirs is None:
            claims.append([f"At {shot.stem.split('-')[-1]} px, the page draws", True, "no original to compare with"])
            continue
        s = png.similarity(mine, theirs)
        scores.append(s)
        claims.append([f"At {shot.stem.split('-')[-1]} px, it looks like the original", s >= p.state["good_enough"], f"{s:.0f}% alike", shot.stem.split("-")[-1]])
    score = sum(scores) / len(scores) if scores else None
    if score is None:
        return result("web", True, "The pages draw at every width (nothing to compare them with).", None, claims)
    detail = ", ".join(f"{c[3]} px {c[2]}" for c in claims if len(c) > 3)
    claims = [c[:3] for c in claims]
    return result("web", all(c[1] for c in claims), f"Looks {score:.0f}% like the original ({detail}). Your screenshots are in {rd.relative_to(p.root)}/, the original's in capture/.", score, claims)


def _run_spec(p: Project) -> Optional[list]:
    run = p.app_spec().get("run")
    return list(run) if run else None


def _word_alike(a: str, b: str) -> float:
    wa, wb = set(a.lower().split()), set(b.lower().split())
    if not wa and not wb:
        return 100.0
    return 100.0 * len(wa & wb) / max(1, len(wa | wb))


def check_runs(p: Project, rd: Path, live) -> dict:
    recorded = read_json(p.capture / "runs.json", {})
    runs = recorded.get("runs") if isinstance(recorded, dict) else None
    if not runs:
        return result("runs", None, "No runs of the original were recorded (start with --allow-run on a program to record them).")
    cmd = _run_spec(p)
    if not cmd:
        return result("runs", False, 'app/craft-app.json has no "run" command, so the rebuild can\'t be run with the same inputs.')
    claims, scores, mine = [], [], []
    for run in runs:
        args = [a for a in run.get("args", []) if isinstance(a, str)]
        live.event("run", " ".join(args) or "(no arguments)")
        r = proc.run([*cmd, *args], cwd=str(p.app), timeout=15, cap=16_000)
        mine.append({"args": args, "code": r.code, "output": r.output, "error": r.error})
        label = " ".join(args) or "no arguments"
        claims.append([f"With {label}, it exits with code {run.get('code')}", r.code == run.get("code"), f"it exits with {r.code}" + (f" ({r.error})" if r.error else "")])
        s = _word_alike(r.output, run.get("output", ""))
        scores.append(s)
        claims.append([f"With {label}, it prints what the original prints", s >= ALIKE, f"{s:.0f}% of the words match"])
    write_atomic(rd / "runs.json", json.dumps({"version": 1, "runs": mine}, indent=1, ensure_ascii=False))
    score = sum(scores) / len(scores)
    bad = [c for c in claims if not c[1]]
    return result("runs", not bad, f"{len(claims) - len(bad)} of {len(claims)} claims hold; output {score:.0f}% alike.", score, claims)


def check_screenshot(p: Project, rd: Path, live) -> dict:
    cmd = _run_spec(p)
    if not cmd:
        return result("screenshot", False, 'app/craft-app.json has no "run" command, so the program can\'t be started.')
    dest = rd / "screenshot.png"
    live.event("run", "starting it with --screenshot")
    r = proc.run([*cmd, "--screenshot", str(dest)], cwd=str(p.app), timeout=90, idle=60)
    g = png.grid(dest) if dest.is_file() else None
    if g is None:
        return result("screenshot", False, f"The program didn't save a readable PNG with --screenshot ({r.error or f'exit {r.code}'}). Contract: start, draw about two seconds of frames, save the window to that file, exit.")
    if g.blank():
        return result("screenshot", False, "The --screenshot picture is one colour: nothing was drawn before saving.")
    refs = [x for x in sorted(p.reference.glob("*.png"))] if p.reference.exists() else []
    best = None
    for ref in refs:
        rg = png.grid(ref)
        if rg is not None:
            s = png.similarity(g, rg)
            best = s if best is None else max(best, s)
    if best is None:
        return result("screenshot", True, f"It starts and draws ({g.width}×{g.height}).")
    return result("screenshot", True, f"It starts and draws ({g.width}×{g.height}); about {best:.0f}% like the closest picture in reference/.", best)


def check_selftest(p: Project, rd: Path, live) -> dict:
    cmd = _run_spec(p)
    if not cmd:
        return result("selftest", False, 'app/craft-app.json has no "run" command, so the game can\'t be started.')
    dest = rd / "self-test.json"
    live.event("run", "playing the core loop with --self-test")
    r = proc.run([*cmd, "--self-test", str(dest)], cwd=str(p.app), timeout=120, idle=90)
    report = read_json(dest)
    if not isinstance(report, dict) or not isinstance(report.get("steps"), list):
        return result("selftest", False, f"The game didn't save a report with --self-test ({r.error or f'exit {r.code}'}). Contract: {{\"version\": 1, \"steps\": [{{\"step\": \"move\", \"passed\": true, \"detail\": \"…\"}}]}} with steps move, act and hud measured from the game's own state.")
    claims = [[str(s.get("step")), bool(s.get("passed")), str(s.get("detail", ""))] for s in report["steps"] if isinstance(s, dict)]
    have = {c[0] for c in claims}
    for need in ("move", "act", "hud"):
        if need not in have:
            claims.append([need, False, "not measured"])
    bad = [c for c in claims if not c[1]]
    return result("selftest", not bad, "The core loop works." if not bad else f"{len(bad)} of {len(claims)} steps don't pass: " + ", ".join(c[0] for c in bad), None, claims)


CHECKS: dict[str, Callable] = {"build": check_build, "tests": check_tests, "web": check_web, "runs": check_runs, "screenshot": check_screenshot, "selftest": check_selftest}


def good(res: dict, good_enough: float) -> bool:
    return all(c["passed"] is not False and (c["score"] is None or c["score"] >= good_enough) for c in res["checks"])


def run_checks(p: Project, round_no: int, ui: UI) -> dict:
    rd = p.round_dir(round_no)
    rd.mkdir(parents=True, exist_ok=True)
    out = []
    ids = tables.KINDS.get(p.state["kind"], tables.KINDS["tool"])["checks"]
    for cid in ids:
        with ui.live(f"check {cid}", "check") as live:
            try:
                res = CHECKS[cid](p, rd, live)
            except Exception as e:  # a check that breaks says so; it never stops the run
                res = result(cid, None, f"The check itself failed: {type(e).__name__}: {e}")
        out.append(res)
        if cid == "build" and res["passed"] is False:
            break  # nothing else can be judged on a build that doesn't build
    res = {"version": 1, "round": round_no, "time": time.strftime("%Y-%m-%dT%H:%M:%S"), "checks": out}
    res["good"] = good(res, p.state["good_enough"])
    write_atomic(rd / "result.json", json.dumps(res, indent=1, ensure_ascii=False))
    p.log(f"check round {round_no}: {'good' if res['good'] else 'not yet'} " + "; ".join(f"{c['id']}={c['passed']}" for c in out))
    return res


def show(res: dict, ui: UI) -> None:
    for c in res["checks"]:
        state = "skip" if c["passed"] is None else ("done" if c["passed"] else "fail")
        first, *rest = c["summary"].splitlines() or [""]
        ui.step(state, c["id"], first, stage="check")
        if c["passed"] is False and rest:
            ui.note("\n".join(rest[-12:]))
        for text, ok, detail in c["claims"]:
            if not ok:
                ui.note(f"{text}: {detail}")


def refine_text(res: dict) -> str:
    """What the builder is told after a round that isn't good yet."""
    lines = [f"Check {res['round']} isn't passing yet:"]
    for c in res["checks"]:
        if c["passed"] is False or (c["score"] is not None and not res["good"]):
            lines.append(f"\n[{c['id']}] {c['summary']}")
            lines += [f"- {t}: {d}" for t, ok, d in c["claims"] if not ok]
    return "\n".join(lines)
