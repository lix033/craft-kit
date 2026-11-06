"""What the builder is told: the first brief, refinements, follow-ups, answers."""

from __future__ import annotations

from . import tables
from .workspace import Project

RULES = """Rules:
- The request comes first. When it names a language, framework, engine or platform, use exactly that; the stack below is only the default for what it leaves open. Never switch away from what was asked to get past a failing build: fix the build.
- Change files only inside app/. Everything else here is read-only evidence.
- Rebuild layout, styling and behaviour yourself from the evidence. Don't copy logos, photos, brand names or long passages of text unless the person says they own them or have permission; use neutral placeholders instead.
- Ask the person only about choices that really change the result, never about technical details you can decide (see "Asking" below).
- Build everything that was asked for. If part of it won't fit this version, ask before leaving it out, with the smaller version as one choice; never drop it silently.
- Never start dev servers, watchers or anything that doesn't exit (npm run dev, vite, cargo watch). The checks serve and run the build themselves.
- Never claim something works that you didn't run. Missing evidence isn't proof: mark what you estimated.
- Finish with 3-5 plain sentences for the person: what you built, what differs from the original or is still unknown, and one idea for what to ask next. No code and no file paths in that summary."""

CONTRACTS = {
    "website": 'The site must build to static files: index.html at the top of a folder, each other page at its own path, working when served as plain files. Name that folder in app/craft-app.json as "site" (for example "dist"; "." for plain HTML in app/). It is photographed at 1440, 768 and 390 px wide and compared with capture/screenshot-<width>.png; it must never scroll sideways on a phone.',
    "cli": 'Declare "run" in app/craft-app.json (for example ["python3", "main.py"] or ["./target/debug/tool"], relative to app/). The check runs it with each input in capture/runs.json and compares the exit code and the printed words with the original\'s.',
    "app": 'Declare "run" in app/craft-app.json. Give the program a `--screenshot <file.png>` option: start normally, draw about two seconds of frames, save the window as a PNG to that file and exit. The check runs it that way; a missing or one-colour picture fails.',
    "game": 'Declare "run" in app/craft-app.json. Give the game `--screenshot <file.png>` (start, draw about two seconds, save the window as PNG, exit) and `--self-test <file.json>`: start a game as a player would, drive it with scripted input for a few seconds, measure from the game\'s own state whether each part of the core loop works, write {"version": 1, "steps": [{"step": "move", "passed": true, "detail": "walked 3 cells"}, {"step": "act", "passed": true, "detail": "…"}, {"step": "hud", "passed": true, "detail": "score and lives drawn"}]} and exit. The game isn\'t ready until every step passes.',
    "tool": "Write tests that prove the features the request names, and declare how to run them in app/craft-app.json.",
}

ASKING = """Asking: when a decision is really the person's, write questions.json in the project folder (not in app/):
{"version": 1, "questions": [{"id": "q1", "question": "Keep the dark theme?", "choices": ["Yes, dark", "Light", "Both, with a switch"]}]}
with 2-4 short choices each, then end your turn with a one-line reason. Their answers arrive in the next message. Keep building whatever doesn't depend on the answer first."""


def mode_text(p: Project) -> str:
    if p.deep:
        return ("Deep mode, for the person's private use: you may look inside the original (its files, its code, a site's HTML and scripts) "
                "to learn how it works. Rebuild what you learn in your own code; never paste the original's code or assets into app/.")
    return ("Clean room: work only from what a visitor or user can see: the screenshots, measurements and runs in capture/, the pictures in reference/ "
            "and the person's words. Never open, read, fetch, run or decompile the original's files, folder, page source or program yourself.")


def target_text(p: Project) -> str:
    t = p.state["target"]
    return {"website": f"the website {t['value']}", "local": f"the program or folder at {t['value']}"}.get(t["type"], "nothing specific (build from the request)")


def first(p: Project) -> str:
    kind = tables.KINDS.get(p.state["kind"], tables.KINDS["tool"])
    stack = tables.stack_by_name(p.state["stack"])
    self_check = "Run `craft check --self` in the project folder: it runs exactly the checks that judge your work and lists what differs. Fix, build and check again until it passes."
    return f"""You are the builder in a craft project: rebuilding software from evidence for a person who may not code.

Request: "{p.state['request']}"
Target: {target_text(p)}
What to build: {kind['goal']}.
Project folder (your working directory): {p.root}

{mode_text(p)}

The folder:
- capture/   evidence gathered by Study. Start with capture/README.md, then open every screenshot and file it lists.
- reference/ pictures or files the person added. Look at each.
- app/       the only folder you change. The whole build lives here.
- checks/    results of earlier checks (round-N/result.json, screenshots, logs).
- unknowns.md  questions the evidence doesn't answer yet; you keep it up to date.

How to build it, unless the request says otherwise: {stack['steps']}

Declare how your build is built, tested and run in app/craft-app.json, each command a list of program and arguments run in app/:
{{"version": 1, "install": ["npm", "install"], "build": ["npm", "run", "build"], "test": ["npm", "test"], "run": ["node", "dist/main.js"], "site": "dist"}}
(leave out what doesn't apply). {CONTRACTS.get(p.state['kind'], CONTRACTS['tool'])}

How to work:
1) Study the evidence, overview first. Where a gap matters to the result, look again (Deep) or ask (Clean room) instead of guessing. Add each open question to unknowns.md as `- [ ] question — what would settle it — impact: high|medium|low`; tick it with the answer and its evidence when settled, and until then say what you did instead (an estimate, a placeholder, a question).
2) Plan: write 3-7 plain-language steps at the top of app/PLAN.md and tick them as you go.
3) Build it in app/ and fix errors until the build succeeds.
4) Test it against the original. {self_check} If `craft` isn't available, run the build, tests and the contract above yourself.
5) Before you reply, go through PLAN.md and unknowns.md once more: settle what one more look can settle, and say what's left.

{RULES}

{ASKING}"""


def refine(p: Project, check_text: str, answers: str = "") -> str:
    return f"""{check_text}

Fix this in app/ (biggest visible or functional differences first), build again until it succeeds, re-run the check, and reply with 1-2 plain sentences on what you changed. The full task is in BRIEF.md if you need it again.{answers}"""


def follow_up(p: Project, message: str, answers: str = "") -> str:
    return f"""The person asks for a change to the build: "{message}"

Keep what works and change only what this needs, in app/. Build and check again until it passes, then reply with 2-3 plain sentences on what changed. The original task and rules are in BRIEF.md.{answers}"""


def resume(p: Project, answers: str = "") -> str:
    return f"""Carry on with the build where you left off. The task and rules are in BRIEF.md; app/PLAN.md, unknowns.md and checks/ show where things stand.{answers}"""


def answers_text(answered: list[dict]) -> str:
    if not answered:
        return ""
    return "\n\nThe person answered your questions:\n" + "\n".join(f"- {q['question']} → {q['answer']}" for q in answered)
