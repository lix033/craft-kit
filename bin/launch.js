"use strict";
// craftkit on npm: the Python package ships inside this one (standard library only), and this
// launcher hands the terminal to Python 3.9+. Nothing is downloaded or installed at install time.

const { spawn, spawnSync } = require("child_process");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const MIN = [3, 9];

function candidates() {
  if (process.env.CRAFT_PYTHON) return [[process.env.CRAFT_PYTHON]]; // a choice, not a hint: no fallback
  const list = [];
  if (process.platform === "win32") list.push(["py", "-3"], ["python"], ["python3"]);
  else list.push(["python3"], ["python"]);
  return list;
}

function works(cmd) {
  const probe = `import sys; print(1 if sys.version_info[:2] >= (${MIN[0]}, ${MIN[1]}) else 0)`;
  try {
    const r = spawnSync(cmd[0], [...cmd.slice(1), "-c", probe], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"], timeout: 15000, windowsHide: true });
    return r.status === 0 && r.stdout.trim() === "1";
  } catch (_) {
    return false;
  }
}

function findPython() {
  for (const cmd of candidates()) if (works(cmd)) return cmd;
  return null;
}

function noPython() {
  const hint = {
    darwin: "brew install python   (or https://www.python.org/downloads/)",
    win32: "winget install Python.Python.3.12   (or https://www.python.org/downloads/)",
  }[process.platform] || "sudo apt install python3   (or your system's package manager)";
  if (process.env.CRAFT_PYTHON) {
    process.stderr.write(` ✗ CRAFT_PYTHON=${process.env.CRAFT_PYTHON} isn't Python ${MIN.join(".")} or newer (or doesn't run).\n   Fix the path, or unset CRAFT_PYTHON to use the system's python3.\n`);
    process.exit(127);
  }
  process.stderr.write(
    ` ✗ craft needs Python ${MIN.join(".")} or newer, and none was found.\n` +
      `   Install it: ${hint}\n` +
      `   Or point to one: CRAFT_PYTHON=/path/to/python3 craft\n`
  );
  process.exit(127);
}

module.exports = function launch(entry) {
  const py = findPython();
  if (!py) noPython();
  // -I: isolated (no current-folder imports, no user site); the package's folder is added explicitly.
  const code = `import sys; sys.path.insert(0, ${JSON.stringify(ROOT)}); from craft_kit.cli import ${entry}; sys.exit(${entry}())`;
  const child = spawn(py[0], [...py.slice(1), "-I", "-c", code, ...process.argv.slice(2)], { stdio: "inherit", windowsHide: false });

  // Ctrl-C reaches Python through the terminal; Node waits for it to stop and leave cleanly.
  const forward = (sig) => () => { try { child.kill(sig); } catch (_) {} };
  process.on("SIGINT", () => {});
  process.on("SIGTERM", forward("SIGTERM"));
  process.on("SIGHUP", forward("SIGHUP"));

  child.on("error", (err) => {
    process.stderr.write(` ✗ Python couldn't start: ${err.message}\n`);
    process.exit(127);
  });
  child.on("exit", (code, signal) => {
    if (signal) process.exit(128 + ({ SIGINT: 2, SIGTERM: 15, SIGHUP: 1 }[signal] || 1));
    process.exit(code === null ? 1 : code);
  });
};
