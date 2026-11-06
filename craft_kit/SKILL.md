---
name: craft
description: Recreate or build any software — a website, CLI, desktop app, game, library or service — by studying an original (or a plain request), building a new project, checking it against the original with measurable checks, and refining until it passes. Use when asked to "recreate", "clone", "rebuild", "make my own version of", or "build something like" an existing site, program or tool, or to build a new tool from a description with verification. Works with or without the `craft` CLI.
---

# Craft: study → build → check → refine

A method for rebuilding any piece of software from evidence, then proving the result is close.
It works the same for a website, a command-line tool, a desktop app, a game or a library. Follow
the five stages in order; never skip Check.

If the `craft` command is installed (`craft --version`), it does the bookkeeping for you: use
`craft new`, `craft study`, `craft check --self` and `craft status` at the matching stages. Without
it, do each stage by hand as written below. The folder layout and contracts are the same either way.

## 0. Intake (one minute, before anything else)

Settle five things. Ask the person only for what you can't infer, in one message, with 2-4 choices
per question.

| Field   | Values | Default |
|---------|--------|---------|
| Request | what they want, in their words | (required) |
| Target  | a URL, a file or folder, a command on PATH, or none | none: build from the request |
| Kind    | `website`, `cli`, `app`, `game`, `tool` (library/API/service) | from the request's words |
| Stack   | whatever the request names | the simplest stack that fits; for a website, whatever the original visibly uses |
| Mode    | **Clean room** or **Deep** | Clean room |

- **Clean room**: use only what a visitor or user sees: screenshots, visible text and measured
  layout of a site; what a program prints when run (only with the person's OK to run it); pictures
  the person provides. Never open, read, fetch or decompile the original's files, page source or
  program.
- **Deep** (the person must say so, for private use): you may look inside: a site's HTML and
  scripts, a folder's files, a program's strings and code. Rebuild what you learn in your own code;
  never paste the original's code or assets into the build.

The request always wins over defaults: if it names a language, framework or engine, use exactly
that, and never switch away from it to get past a failing build.

## 1. Workspace

Create one project folder (`craft new` does this):

```text
<project>/
  craft.json       request, target, kind, stack, mode, round counters (versioned)
  BRIEF.md         the task as given to the builder
  capture/         evidence from Study — README.md first. Read-only.
  reference/       pictures/files from the person. Read-only.
  app/             THE ONLY FOLDER THE BUILD CHANGES
  checks/round-N/  each check: result.json, screenshots, logs
  checks/turn-N/   each builder turn: message sent, log, reply
  unknowns.md      open questions about the original
  questions.json   questions for the person, with their answers
```

Keeping evidence (`capture/`) apart from the build (`app/`) is what makes the checks honest.

## 2. Study — gather evidence into `capture/`

Overview first, details after. Write `capture/README.md` as the index of everything you found.

| Target | Clean room | Deep adds |
|--------|------------|-----------|
| Website | full-page screenshots at **1440, 768, 390 px** (`screenshot-<w>.png`); visible facts: title, headings, navigation, buttons, computed fonts/colours/sizes, section count, visible text | the served HTML (`page.html`), scripts, network requests |
| CLI program | with permission, run it with no args, `--help`, `--version`, `-h` (stdin closed, 10 s limit); record exit code + output in `runs.json` | its strings (`strings.txt`), file type |
| App / game | the person's pictures in `reference/`; a screenshot of its window if allowed | its files, manifests, config values, strings |
| Folder / repo | nothing inside is read | inventory by file type, manifests (package.json, Cargo.toml…), README |
| None | the request alone | — |

Record each question the evidence doesn't answer in `unknowns.md`:

```text
- [ ] Does the menu collapse on phones? — open it at 390 px — impact: high
```

Tick it later with the answer and the evidence that settled it. Missing evidence is never proof:
mark what you estimate.

## 3. Build — only inside `app/`

1. **Plan**: 3-7 plain-language steps at the top of `app/PLAN.md`; tick them as you go.
2. **Build** in the chosen stack until the build command succeeds.
3. **Declare** how the build is built, tested and run in `app/craft-app.json` (commands are lists
   run inside `app/`; leave out what doesn't apply):

   ```json
   {"version": 1, "install": ["npm", "install"], "build": ["npm", "run", "build"],
    "test": ["npm", "test"], "run": ["node", "dist/main.js"], "site": "dist"}
   ```

4. **Meet the kind's contract** — this is what Check runs:

| Kind | Contract |
|------|----------|
| website | static files with `index.html` at the top of `site`; each page at its own path; no sideways scroll on a phone |
| cli | `run` prints the same as the original for each recorded input and exits with the same code |
| app | `run --screenshot <file.png>`: start, draw ~2 s, save the window as PNG, exit |
| game | `--screenshot` as above, plus `run --self-test <file.json>`: play the core loop with scripted input and write `{"version":1,"steps":[{"step":"move","passed":true,"detail":"…"},{"step":"act",…},{"step":"hud",…}]}` measured from the game's own state |
| tool | tests that prove each feature the request names |

Rules while building:
- Rebuild layout, style and behaviour from the evidence. No logos, photos, brand names or long
  copied text unless the person owns them or has permission; use neutral placeholders.
- Ask the person only about choices that change the result (write `questions.json` with 2-4
  choices, keep building what doesn't depend on it). Never ask about technical details.
- Build everything asked. If part of it won't fit, ask before dropping it; never drop it silently.
- Never start dev servers or watchers (`npm run dev`, `vite`, `cargo watch`): Check serves and runs
  the build itself.

## 4. Check — measure, don't guess

Run the same checks every round (`craft check --self` while building; `craft check` records a
round). Stop at the first failing build: nothing else can be judged.

| Check | Applies to | Passes when |
|-------|-----------|-------------|
| build | all | install + build commands exit 0 |
| web | website | serve `site` on 127.0.0.1, screenshot at the same three widths, compare with `capture/` per width; similarity ≥ the threshold (default 90%) |
| runs | cli | every recorded input: same exit code, ≥ 80% of printed words in common |
| screenshot | app, game | a readable, non-blank PNG; compared with `reference/` pictures when present |
| selftest | game | every core-loop step (move, act, hud) passes |
| tests | all | the project's tests pass ("no tests" is noted, not a failure) |

A check that couldn't look (no browser, no recording) says so: it's "not judged", never "passed".
Save each round's result as `checks/round-N/result.json`.

## 5. Refine — then Ready

- Feed the failing checks back as the next task: biggest visible or functional differences first,
  with the measured numbers. Rebuild, re-check.
- Stop when every check passes, **or** after **6 refinements per request** (the count survives
  retries; only a new request resets it), **or** when two turns in a row change nothing in `app/`
  (stuck: ask the person for detail instead of looping).
- Before finishing, re-read `PLAN.md` and `unknowns.md`; settle what one more look can settle.

**Ready** = a summary for the person in 3-5 plain sentences: what was built, what differs from
the original or is still unknown, and one idea for what to ask next. No code, no file paths. Then
how to open it (`craft open`) and how to ask for a change (`craft run "…"`).

## Honesty rules (always)

- Never claim something works that you didn't run. Report what you verified and what you didn't.
- Every external program you start gets a time limit and no interactive stdin.
- Keep secrets out of the project: no keys or tokens in `app/`, `capture/` or logs.
