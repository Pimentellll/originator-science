#!/usr/bin/env python3
"""MIRAGE launcher. Run through ``./mirage``; standard library only (Python 3.9+).

    ./mirage setup | doctor | demo | dev | test | smoke | benchmark-dev | stop | clean-runtime | help

Bootstrap installs only into ``.venv`` and ``frontend/node_modules``; runtime state is in
``.local/mirage`` (git-ignored). Global Python packages are never modified.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request

import mirage_env as E

HELP = """\
MIRAGE: one-command launcher

  ./mirage demo [--scenario S] [--seed N] [--no-browser]   set up if needed, start API + cockpit, open browser
  ./mirage dev                                             API + cockpit with prefixed [API]/[WEB] logs, hot reload
  ./mirage setup [--force] [--skip-frontend]               create .venv, install Python + frontend deps (idempotent)
  ./mirage doctor [--json]                                 diagnose the environment; exit 0 = ready
  ./mirage test [--quick | --scientific] [--list]          grouped test run (software bugs vs scientific gates)
  ./mirage smoke                                           deterministic H0 campaign + trust-boundary smoke
  ./mirage benchmark-dev                                   small DEVELOPMENT-split benchmark into .local (never held-out)
  ./mirage stop                                            stop MIRAGE-owned API/cockpit processes only
  ./mirage clean-runtime [--all] [--yes]                   delete .local runtime state (--all also .venv + node_modules)
  ./mirage help

demo/dev options:
  --scenario  COMPOUND_FAILURE (default) | SINGLE_FAILURE | ASSAY_FAILURE | MODEL_FAILURE | MIXED
  --scenario-version  SEMANTICS_V2 (default) | BASELINE_V1
  --policy    rescue_planner (default) | greedy_eig | fixed_pipeline | random
  --seed N    campaign seed (default 9)
  --port N --frontend-port N   preferred ports (default 8000 / 5173; another free port is chosen if busy)
  --no-browser                 do not open a browser
  --docker                     use docker compose instead of native processes (fallback)
"""

SCENARIOS = ("COMPOUND_FAILURE", "SINGLE_FAILURE", "ASSAY_FAILURE", "MODEL_FAILURE", "MIXED")


# ------------------------------------------------------------------ setup
def _step(msg: str) -> None:
    print(f"\n{E.paint('▸', 'cyan')} {msg}")


def _stream(argv: list[str], *, cwd=None, env=None) -> int:
    """Run a long install with output shown (installs can take minutes; silence looks hung)."""
    return subprocess.run(argv, cwd=cwd, env=env, check=False).returncode


def ensure_uv() -> str | None:
    uv = E.find_uv()
    if uv:
        return uv
    E.warn("uv not found; installing it to ~/.local/bin via the official installer (no sudo, no global Python changes)")
    try:
        if shutil.which("curl"):
            fetched = subprocess.run(["curl", "-LsSf", E.UV_INSTALL_URL], capture_output=True, check=False, timeout=120)
            script = fetched.stdout if fetched.returncode == 0 else b""
        else:  # astral.sh rejects urllib's default User-Agent
            req = urllib.request.Request(E.UV_INSTALL_URL, headers={"User-Agent": "curl/8.5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - official installer
                script = resp.read()
        if script:
            proc = subprocess.run(["sh"], input=script, env={**os.environ, "UV_NO_MODIFY_PATH": "1"}, check=False)
            if proc.returncode == 0 and E.find_uv():
                E.ok("installed uv")
                return E.find_uv()
    except Exception as exc:  # noqa: BLE001
        E.warn(f"could not download the uv installer: {exc}")
    E.warn("uv unavailable; falling back to python -m venv + pip (slower but equivalent). Manual uv install: curl -LsSf https://astral.sh/uv/install.sh | sh")
    return None


def _install_python_deps(uv: str | None) -> bool:
    target = str(E.ROOT)
    spec = f"{target}[{E.PROJECT_EXTRAS}]"
    linux = E.detect_platform().system == "linux"
    attempts = [True, False] if linux else [False]  # first try CPU-only torch (small), then default index
    for cpu_index in attempts:
        if uv:
            argv = [uv, "pip", "install", "--python", str(E.venv_python()), "-e", spec]
            if cpu_index:
                argv += ["--extra-index-url", E.TORCH_CPU_INDEX, "--index-strategy", "unsafe-best-match"]
        else:
            argv = [str(E.venv_python()), "-m", "pip", "install", "--disable-pip-version-check", "-e", spec]
            if cpu_index:
                argv += ["--extra-index-url", E.TORCH_CPU_INDEX]
        if _stream(argv, cwd=E.ROOT, env=E.project_env()) == 0:
            return True
        if cpu_index:
            E.warn("install with the CPU-only PyTorch index failed; retrying with the default index")
    return False


def python_ready() -> bool:
    vpy = E.venv_python()
    if not vpy.exists():
        return False
    if E.read_stamp("python").get("key") != E.python_stamp_key():
        return False
    probe = "import mirage,fastapi,uvicorn,numpy,gymnasium,stable_baselines3,sb3_contrib,pytest,sys;from pathlib import Path;sys.exit(0 if Path(mirage.__file__).resolve().is_relative_to(Path(sys.argv[1])) else 1)"
    return subprocess.run([str(vpy), "-c", probe, str(E.ROOT / "src")], env=E.project_env({"PYTHONPATH": ""}),
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0


def needs_setup() -> bool:
    return not python_ready() or not E.frontend_deps_ready()


def cmd_setup(argv: list[str]) -> int:
    force = "--force" in argv
    skip_frontend = "--skip-frontend" in argv
    E.banner("Setup")

    # 1. platform
    plat = E.detect_platform()
    if not plat.supported:
        E.fail(f"unsupported platform: {plat.label}")
        print(E.WINDOWS_MESSAGE if plat.system == "windows" else "Supported: Ubuntu 24.04, WSL2 Ubuntu, Linux; macOS secondary.")
        return 1
    E.ok(f"platform: {plat.label}")

    # 2. git
    git = E.version_of(["git", "--version"]) if shutil.which("git") else None
    if not git:
        E.fail("git not found.  Fix: sudo apt install git   (macOS: xcode-select --install)")
        return 1
    E.ok(f"git {git}")

    # 3. node / npm (checked before the slow Python install so problems surface early)
    node = E.version_of(["node", "--version"]) if shutil.which("node") else None
    npm = E.version_of(["npm", "--version"]) if shutil.which("npm") else None
    if not skip_frontend:
        if not node or not npm or not E.node_ok(node):
            E.fail(f"Node/npm {'too old (' + node + ')' if node else 'not found'}; the cockpit needs Node 20.19+ or 22.12+ with npm.")
            print("  Fix: curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash && exec bash && nvm install 22")
            print("       (macOS: brew install node@22)   Backend only: ./mirage setup --skip-frontend")
            return 1
        E.ok(f"node {node}, npm {npm}")

    # 4. python + venv
    uv = ensure_uv()
    if uv:
        E.ok(f"uv {E.version_of([uv, '--version'])}")
    vpy = E.venv_python()
    if vpy.exists() and E.parse_version(E.version_of([str(vpy), "--version"]) or "0")[:2] < E.MIN_PYTHON:
        E.warn(".venv uses Python < 3.11; recreating it")
        shutil.rmtree(E.VENV)
    if not vpy.exists():
        _step("Creating .venv")
        system = E.find_system_python()
        if uv:
            argv_v = [uv, "venv", str(E.VENV), "--python", system[0] if system else "3.12"]
            rc = _stream(argv_v, cwd=E.ROOT)
        elif system:
            rc = _stream([system[0], "-m", "venv", str(E.VENV)], cwd=E.ROOT)
        else:
            E.fail("Python >= 3.11 not found and uv is unavailable.")
            print("  Fix: sudo apt install python3 python3-venv   (Ubuntu 24.04 ships 3.12)   or install uv: curl -LsSf https://astral.sh/uv/install.sh | sh")
            return 1
        if rc != 0 or not vpy.exists():
            E.fail("could not create .venv.  On Ubuntu: sudo apt install python3-venv, then re-run ./mirage setup")
            return 1
    E.ok(f"python {E.version_of([str(vpy), '--version'])} in .venv")

    # 5. python deps (single authoritative path: pyproject.toml extras)
    if python_ready() and not force:
        E.ok("Python dependencies already installed (pyproject.toml unchanged)")
    else:
        _step(f"Installing MIRAGE + [{E.PROJECT_EXTRAS}] into .venv (first run downloads PyTorch; this can take a few minutes)")
        if not _install_python_deps(uv):
            E.fail("dependency install failed. Check your network/proxy, then re-run ./mirage setup. Manual path: .venv/bin/pip install -e \".[dev,rl]\"")
            return 1
        E.write_stamp("python", {"key": E.python_stamp_key()})
        if not python_ready():
            E.fail("installed, but the project imports failed. Run ./mirage doctor for details.")
            return 1
        E.ok("Python dependencies installed")

    # 6. frontend deps
    if skip_frontend:
        E.warn("frontend skipped (--skip-frontend)")
    elif E.frontend_deps_ready() and not force:
        E.ok("frontend dependencies already installed (package-lock.json unchanged)")
    else:
        _step("Installing frontend dependencies (npm ci)")
        if _stream(["npm", "ci", "--no-audit", "--no-fund"], cwd=E.FRONTEND) != 0:
            E.fail("npm ci failed. Fixes: check network/proxy; rm -rf frontend/node_modules && ./mirage setup; use Node 22 LTS")
            return 1
        E.write_stamp("frontend", {"key": E.frontend_stamp_key()})
        E.ok("frontend dependencies installed")

    # 7. runtime dirs
    for d in (E.PIDS, E.LOGS, E.STAMPS, E.RECORDS):
        d.mkdir(parents=True, exist_ok=True)

    print()
    E.ok("MIRAGE is set up.")
    E.info("Next: ./mirage doctor   ·   ./mirage test --quick   ·   ./mirage demo")
    return 0


# ------------------------------------------------------------------ simple commands
def cmd_doctor(argv: list[str]) -> int:
    import doctor

    return doctor.main(argv)


def cmd_smoke(_: list[str]) -> int:
    if not E.venv_python().exists():
        E.fail("no .venv yet. Run: ./mirage setup")
        return 1
    E.banner("Smoke test")
    print(E.paint("deterministic H0 campaign (scripts/h0_smoke.py)", "dim"))
    proc = E.run([str(E.venv_python()), "scripts/h0_smoke.py"], cwd=E.ROOT, env=E.project_env(), timeout=300)
    print(proc.stdout.strip())
    if proc.returncode != 0 or "replay_frames=" not in (proc.stdout or ""):
        E.fail("H0 smoke failed")
        return 1
    import doctor

    rows = [c for c in doctor.project_checks() if c.name in ("trust-boundary smoke", "deterministic scientific smoke", "record / replay")]
    bad = False
    for c in rows:
        (E.ok if c.status == "pass" else E.fail)(f"{c.name}: {c.detail}")
        bad = bad or c.status != "pass"
    return 1 if bad else 0


def cmd_benchmark_dev(_: list[str]) -> int:
    if not E.venv_python().exists():
        E.fail("no .venv yet. Run: ./mirage setup")
        return 1
    out = E.LOCAL / "benchmark-dev"
    E.banner("Benchmark (development split)")
    E.info(f"development seeds only, 2 episodes per archetype, output in {out.relative_to(E.ROOT)}")
    E.info("held-out seeds and results/ are never touched by this command.")
    return _stream([str(E.venv_python()), "scripts/run_binder_benchmark.py", "--split", "development", "--per-archetype", "2",
                    "--out", str(out), "--benchmark-id", "binder-campaign-dev"], cwd=E.ROOT, env=E.project_env())


def cmd_test(argv: list[str]) -> int:
    import run_tests

    return run_tests.main(argv)


def cmd_stop(_: list[str]) -> int:
    stopped = 0
    for role in ("supervisor", "api", "web"):
        pid = E.owned_pid(role)
        if pid is None:
            rec = E.read_pidfile(role)
            if rec:
                E.warn(f"{role}: stale pid file (pid {rec.get('pid')} is gone or not a MIRAGE process); removing")
                E.remove_pidfile(role)
            continue
        if pid == os.getpid():
            continue
        if (E.terminate_process(pid) if role == "supervisor" else E.terminate_group(pid)):
            E.ok(f"stopped {role} (pid {pid})")
            stopped += 1
        else:
            E.fail(f"could not stop {role} (pid {pid})")
            return 1
        E.remove_pidfile(role)
    if not stopped:
        E.info("no MIRAGE-owned processes were running")
    return 0


def cmd_clean_runtime(argv: list[str]) -> int:
    everything = "--all" in argv
    cmd_stop([])
    disposable = [E.LOCAL, E.ROOT / ".pytest_cache", E.FRONTEND / "dist", E.FRONTEND / "node_modules" / ".vite"]
    heavy = [E.VENV, E.FRONTEND / "node_modules"] if everything else []
    if heavy and "--yes" not in argv:
        names = ", ".join(str(p.relative_to(E.ROOT)) for p in heavy)
        if not sys.stdin.isatty():
            E.fail(f"--all would delete {names}; refusing without a terminal. Re-run with --yes to confirm.")
            return 1
        if input(f"Delete {names}? You will need ./mirage setup again. [y/N] ").strip().lower() != "y":
            print("aborted")
            return 1
    for path in disposable + heavy:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            E.ok(f"removed {path.relative_to(E.ROOT)}")
    E.info("kept: results/, checkpoints, tracked files" + ("" if everything else ", .venv, node_modules"))
    return 0


def cmd_demo(argv: list[str], *, dev: bool = False) -> int:
    import supervisor

    return supervisor.main(argv, dev=dev)


COMMANDS = {
    "setup": cmd_setup,
    "doctor": cmd_doctor,
    "demo": cmd_demo,
    "dev": lambda a: cmd_demo(a, dev=True),
    "test": cmd_test,
    "smoke": cmd_smoke,
    "benchmark-dev": cmd_benchmark_dev,
    "stop": cmd_stop,
    "clean-runtime": cmd_clean_runtime,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("help", "-h", "--help"):
        print(HELP)
        return 0
    cmd, rest = argv[0], argv[1:]
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(line_buffering=True)  # readable when piped or redirected
    if cmd not in COMMANDS:
        E.fail(f"unknown command: {cmd}")
        print(HELP)
        return 2
    if E.detect_platform().system == "windows":
        print(E.WINDOWS_MESSAGE)
        return 1
    try:
        return COMMANDS[cmd](rest)
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
