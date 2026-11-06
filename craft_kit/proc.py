"""Running other programs without ever hanging: stdin closed or piped, wall-clock and idle deadlines,
output drained on a thread and capped, the whole process group killed on timeout or Ctrl-C."""

from __future__ import annotations

import os
import queue
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

WINDOWS = os.name == "nt"


@dataclass
class Result:
    code: Optional[int]
    output: str = ""
    timed_out: bool = False
    error: str = ""  # why it couldn't start or was stopped, in plain words
    lines: int = 0
    meta: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.code == 0 and not self.timed_out and not self.error

    def tail(self, n: int = 30) -> str:
        return "\n".join(self.output.rstrip().splitlines()[-n:])


def which(program: str) -> Optional[str]:
    return shutil.which(program)


def _kill(p: subprocess.Popen) -> None:
    try:
        if WINDOWS:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        else:
            os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=3)
                return
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        p.kill()
        p.wait(timeout=3)
    except (OSError, subprocess.SubprocessError):
        pass


def run(
    argv: Sequence[str],
    cwd: Optional[str] = None,
    timeout: float = 600,
    idle: Optional[float] = None,
    input_text: Optional[str] = None,
    on_line: Optional[Callable[[str], None]] = None,
    cap: int = 400_000,
    env: Optional[dict] = None,
) -> Result:
    if not argv:
        return Result(None, error="nothing to run")
    exe = which(argv[0]) or argv[0]
    if not os.path.isabs(exe) and os.sep not in exe and not which(exe):
        return Result(None, error=f"`{argv[0]}` isn't installed or isn't on your PATH")
    kwargs: dict = {}
    if WINDOWS:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        kwargs["start_new_session"] = True
    try:
        p = subprocess.Popen(
            [exe, *argv[1:]],
            cwd=cwd,
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={**os.environ, **(env or {})},
            **kwargs,
        )
    except FileNotFoundError:
        return Result(None, error=f"`{argv[0]}` isn't installed or isn't on your PATH")
    except OSError as e:
        return Result(None, error=f"`{argv[0]}` couldn't start: {e}")

    lines: "queue.Queue[Optional[str]]" = queue.Queue()

    def feed() -> None:
        try:
            assert p.stdin is not None
            p.stdin.write(input_text.encode("utf-8", "replace"))  # type: ignore[union-attr]
            p.stdin.close()
        except (OSError, ValueError):
            pass

    def drain() -> None:
        try:
            assert p.stdout is not None
            for raw in iter(p.stdout.readline, b""):
                lines.put(raw.decode("utf-8", "replace"))
        except (OSError, ValueError):
            pass
        finally:
            lines.put(None)

    if input_text is not None:
        threading.Thread(target=feed, daemon=True).start()
    threading.Thread(target=drain, daemon=True).start()

    out: list[str] = []
    size = 0
    count = 0
    start = last = time.monotonic()
    timed_out = False
    error = ""
    try:
        while True:
            try:
                line = lines.get(timeout=0.25)
            except queue.Empty:
                now = time.monotonic()
                if now - start > timeout:
                    timed_out, error = True, f"stopped after {int(timeout)} s (time limit)"
                    break
                if idle is not None and now - last > idle:
                    timed_out, error = True, f"stopped after {int(idle)} s with no output"
                    break
                continue
            if line is None:
                break
            last = time.monotonic()
            count += 1
            out.append(line)
            size += len(line)
            while size > cap and len(out) > 1:
                size -= len(out.pop(0))
            if on_line is not None:
                try:
                    on_line(line.rstrip("\n"))
                except Exception:  # a display callback must never stop the run
                    pass
    except KeyboardInterrupt:
        _kill(p)
        raise
    if timed_out:
        _kill(p)
    try:
        code = p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _kill(p)
        code = p.poll()
    return Result(None if timed_out else code, "".join(out), timed_out, error, count)
