"""Photographing pages as a visitor sees them, with Playwright: the Python package when it's
installed, else the Playwright CLI through npx. Nothing here reads a page's source."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator, Optional

from . import proc, tables

HEIGHT = 900
FULL_HEIGHT = 2400  # Chrome photographs the window, not the whole page: make it tall
INSTALL_HINT = f"Install a browser for screenshots: `pip install playwright && playwright install chromium`, or `npx -y {tables.PLAYWRIGHT} install chromium`."

# What a visitor can see, measured in the page (no source is saved).
FACTS_JS = """() => {
  const pick = (sel) => { const e = document.querySelector(sel); if (!e) return null;
    const s = getComputedStyle(e);
    return {font: s.fontFamily, size: s.fontSize, weight: s.fontWeight, color: s.color, background: s.backgroundColor, radius: s.borderRadius}; };
  const text = (sel, n) => Array.from(document.querySelectorAll(sel)).slice(0, n).map(e => e.innerText.trim()).filter(Boolean);
  return {
    title: document.title,
    width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight,
    styles: {body: pick('body'), h1: pick('h1'), h2: pick('h2'), link: pick('a'), button: pick('button, .btn, [role=button]'), nav: pick('nav, header')},
    headings: text('h1, h2, h3', 60), links: text('nav a, header a', 40), buttons: text('button, [role=button]', 40),
    sections: document.querySelectorAll('section, main > *').length,
    text: document.body ? document.body.innerText.slice(0, 20000) : ''
  };
}"""


CHROME_NAMES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge", "microsoft-edge"]
CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def chrome() -> Optional[str]:
    if os.environ.get("CRAFT_CHROME"):
        return os.environ["CRAFT_CHROME"]
    for n in CHROME_NAMES:
        found = proc.which(n)
        if found:
            return found
    return next((p for p in CHROME_PATHS if os.path.isfile(p)), None)


def engine() -> Optional[str]:
    """Python Playwright (screenshots + visible facts), else an installed Chrome/Edge in headless
    mode (screenshots), else the Playwright CLI through npx (downloads it on first use)."""
    forced = os.environ.get("CRAFT_BROWSER")
    if forced in ("python", "chrome", "npx", "none"):
        return None if forced == "none" else forced
    try:
        import playwright.sync_api  # type: ignore  # noqa: F401

        return "python"
    except ImportError:
        pass
    if chrome():
        return "chrome"
    return "npx" if proc.which("npx") else None


def _chrome_shot(url: str, dest: Path, width: int) -> tuple[bool, str]:
    exe = chrome()
    if not exe:
        return False, "no Chrome or Edge found"
    with tempfile.TemporaryDirectory(prefix="craft-chrome-") as profile:  # never the person's own profile
        r = proc.run(
            [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
             f"--user-data-dir={profile}", f"--window-size={width},{FULL_HEIGHT}", "--virtual-time-budget=4000",
             f"--screenshot={dest}", url],
            timeout=120,
            idle=90,
        )
    return dest.is_file(), r.error or r.tail(3)


def capture(url: str, out: Path, widths: list[int], facts: bool, live=None) -> tuple[list[Path], dict, list[str]]:
    """Screenshots at each width (screenshot-<w>.png), visitor facts at the first width when the
    Python engine is there, and the problems met, in plain words."""
    out.mkdir(parents=True, exist_ok=True)
    kind = engine()
    if kind is None:
        return [], {}, [f"No browser to photograph pages. {INSTALL_HINT}"]
    if kind == "python":
        return _capture_python(url, out, widths, facts)
    shots, problems = [], []
    if kind == "chrome":
        for w in widths:
            if live:
                live.event("web", f"screenshot at {w} px")
            dest = out / f"screenshot-{w}.png"
            ok, why = _chrome_shot(url, dest, w)
            if ok:
                shots.append(dest)
            else:
                problems.append(f"{w} px: {why}")
        return shots, {}, problems
    for w in widths:
        if live:
            live.event("web", f"screenshot at {w} px")
        dest = out / f"screenshot-{w}.png"
        r = proc.run(
            ["npx", "-y", tables.PLAYWRIGHT, "screenshot", "--full-page", f"--viewport-size={w},{HEIGHT}", "--wait-for-timeout=1500", url, str(dest)],
            timeout=240,
            idle=180,
        )
        if r.ok and dest.is_file():
            shots.append(dest)
        else:
            problems.append(f"{w} px: {r.error or r.tail(3)}")
    if problems and not shots:
        problems.append(INSTALL_HINT)
    return shots, {}, problems


def _capture_python(url: str, out: Path, widths: list[int], facts: bool) -> tuple[list[Path], dict, list[str]]:
    from playwright.sync_api import Error, sync_playwright  # type: ignore

    shots: list[Path] = []
    found: dict = {}
    problems: list[str] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                for i, w in enumerate(widths):
                    page = browser.new_page(viewport={"width": w, "height": HEIGHT})
                    try:
                        page.goto(url, wait_until="networkidle", timeout=60_000)
                    except Error:
                        page.wait_for_timeout(1500)  # a page that never goes quiet still has something to see
                    page.wait_for_timeout(800)
                    dest = out / f"screenshot-{w}.png"
                    page.screenshot(path=str(dest), full_page=True)
                    shots.append(dest)
                    if facts:
                        try:
                            found[str(w)] = page.evaluate(FACTS_JS) if i == 0 else {k: v for k, v in page.evaluate(FACTS_JS).items() if k in ("width", "height", "styles", "sections")}
                        except Error as e:
                            problems.append(f"couldn't measure the page at {w} px: {e}")
                    page.close()
            finally:
                browser.close()
    except Exception as e:  # Playwright raises its own errors, and a missing browser is one of them
        problems.append(f"the browser failed: {str(e).splitlines()[0] if str(e) else type(e).__name__}. {INSTALL_HINT}")
    return shots, found, problems


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # keep the terminal clean
        pass


@contextmanager
def serve(folder: Path) -> Iterator[str]:
    """Serve a folder on loopback for as long as the block runs."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Quiet, directory=str(folder)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()


def facts_markdown(facts: dict) -> str:
    if not facts:
        return ""
    first = facts.get(next(iter(facts)), {})
    lines = ["## What a visitor sees", ""]
    if first.get("title"):
        lines.append(f"Title: {first['title']}")
    for w, f in facts.items():
        lines.append(f"- {w} px: page {f.get('width')}×{f.get('height')} px, {f.get('sections')} sections")
    styles = first.get("styles") or {}
    if styles:
        lines += ["", "Styles (computed, first width):", "```json", json.dumps(styles, indent=1, ensure_ascii=False), "```"]
    for key, label in (("headings", "Headings"), ("links", "Navigation"), ("buttons", "Buttons")):
        if first.get(key):
            lines.append(f"\n{label}: " + " · ".join(first[key][:30]))
    lines.append("\nThe visible text is in capture.json (`text`).")
    return "\n".join(lines) + "\n"
