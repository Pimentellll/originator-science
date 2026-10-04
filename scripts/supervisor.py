"""``./mirage demo`` and ``./mirage dev``: start the API and the Vite cockpit, wait until both are
healthy, open the browser, and shut both down cleanly. Standard library only.

Children run in their own process groups and are tracked in ``.local/mirage/pids`` so that
``./mirage stop`` can find them (verified by command line) and never touches unrelated programs.
"""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import doctor
import mirage_env as E
from benchmark_command import development_benchmark_argv

SCENARIOS = ("COMPOUND_FAILURE", "SINGLE_FAILURE", "ASSAY_FAILURE", "MODEL_FAILURE", "MIXED")
VERSIONS = ("SEMANTICS_V2", "BASELINE_V1")
POLICIES = ("rescue_planner", "greedy_eig", "fixed_pipeline", "random")
DEFAULTS = {"seed": 9, "scenario": "COMPOUND_FAILURE", "version": "SEMANTICS_V2", "policy": "rescue_planner"}
STARTUP_TIMEOUT = 90.0


def parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="mirage demo", add_help=True)
    p.add_argument("--scenario", default=DEFAULTS["scenario"], choices=SCENARIOS, type=str.upper)
    p.add_argument("--scenario-version", dest="version", default=DEFAULTS["version"], choices=VERSIONS, type=str.upper)
    p.add_argument("--policy", default=DEFAULTS["policy"], choices=POLICIES)
    p.add_argument("--seed", type=int, default=DEFAULTS["seed"])
    p.add_argument("--port", type=int, default=E.DEFAULT_API_PORT)
    p.add_argument("--frontend-port", type=int, default=E.DEFAULT_WEB_PORT)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--no-benchmark", action="store_true", help="skip background development benchmark generation")
    p.add_argument("--open", action="store_true", help="dev mode: also open the browser")
    p.add_argument("--guided", action="store_true", help="open straight into the guided demo")
    p.add_argument("--docker", action="store_true", help="run with docker compose instead of native processes")
    p.add_argument("--verbose", action="store_true", help="demo mode: stream service logs too")
    ns = p.parse_args(argv)
    if ns.seed < 0:
        p.error("--seed must be >= 0")
    return ns


# ------------------------------------------------------------------ browser
def open_browser(url: str) -> bool:
    """Best effort, never blocks and never raises. WSL prefers the Windows default browser."""
    plat = E.detect_platform()
    candidates: list[list[str]] = []
    if plat.wsl:
        if shutil.which("wslview"):
            candidates.append(["wslview", url])
        if shutil.which("powershell.exe"):
            candidates.append(["powershell.exe", "-NoProfile", "-Command", f"Start-Process '{url}'"])
        if shutil.which("cmd.exe"):
            candidates.append(["cmd.exe", "/c", "start", "", url.replace("&", "^&")])
    if plat.system == "macos" and shutil.which("open"):
        candidates.append(["open", url])
    if plat.system == "linux" and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or plat.wsl):
        if shutil.which("xdg-open"):
            candidates.append(["xdg-open", url])
    for argv in candidates:
        try:
            proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            try:
                if proc.wait(timeout=8) == 0:
                    return True
            except subprocess.TimeoutExpired:
                return True  # launcher still running (e.g. xdg-open handing off): assume it worked
        except OSError:
            continue
    try:
        return bool(plat.system in ("linux", "macos") and not plat.wsl and (os.environ.get("DISPLAY") or plat.system == "macos") and webbrowser.open(url))
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------ services
class Service:
    def __init__(self, role: str, label: str, argv: list[str], cwd: Path, env: dict, port: int, color: str) -> None:
        self.role, self.label, self.argv, self.cwd, self.env, self.port, self.color = role, label, argv, cwd, env, port, color
        self.log = E.LOGS / f"{role}.log"
        self.proc: subprocess.Popen | None = None
        self._echo = False

    def start(self, echo: bool) -> None:
        E.LOGS.mkdir(parents=True, exist_ok=True)
        self._echo = echo
        self.proc = subprocess.Popen(self.argv, cwd=self.cwd, env=self.env, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                                     start_new_session=True)
        E.write_pidfile(self.role, self.proc.pid, port=self.port, cmd=self.argv[:3])
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        assert self.proc and self.proc.stdout
        prefix = E.paint(f"[{self.label}]", self.color)
        with open(self.log, "w", encoding="utf-8") as fh:
            for line in self.proc.stdout:
                fh.write(line)
                fh.flush()
                if self._echo:
                    print(f"{prefix} {line.rstrip()}", flush=True)

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self) -> None:
        if self.proc is not None:
            if self.proc.poll() is None:
                E.terminate_group(self.proc.pid)
            try:
                self.proc.wait(timeout=3)  # reap: no zombies
            except subprocess.TimeoutExpired:
                pass
            if self.proc.stdout:
                try:
                    self.proc.stdout.close()
                except OSError:
                    pass
        E.remove_pidfile(self.role)


def wait_for(check, services: list[Service], timeout: float) -> str | None:
    """None when ``check()`` passes; otherwise the label of the failed service or 'timeout'."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for s in services:
            if not s.alive:
                return s.label
        if check():
            return None
        time.sleep(0.4)
    return "timeout"


def show_failure(label: str, services: list[Service]) -> None:
    E.fail(f"{label} did not become healthy" if label != "timeout" else "services did not become healthy in time")
    for s in services:
        print(E.paint(f"\n── last lines of {s.log.relative_to(E.ROOT)} ──", "dim"))
        print(E.tail(s.log, 25))
    print("\nSee docs/TROUBLESHOOTING.md. Common causes: a port taken by another program, a half-installed environment (run ./mirage setup --force).")


def start_development_benchmark(no_benchmark: bool) -> subprocess.Popen | None:
    if no_benchmark:
        return None
    summaries = E.LOCAL / "benchmark-dev" / "binder_campaign" / "privileged" / "summaries"
    if next(summaries.glob("*.json"), None) is not None:
        return None
    try:
        proc = subprocess.Popen(
            development_benchmark_argv(),
            cwd=E.ROOT,
            env=E.project_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as exc:
        E.fail(f"could not start development-split benchmark generation: {exc}")
        return None
    E.info("generating the development-split benchmark in the background (~30 s); Benchmark Lab fills in when it finishes")
    return proc


def report_benchmark_exit(proc: subprocess.Popen) -> bool:
    returncode = proc.poll()
    if returncode is None:
        return False
    if returncode == 0:
        E.ok("development-split benchmark generation finished")
    else:
        E.fail(f"development-split benchmark generation failed (exit {returncode})")
    return True


def stop_development_benchmark(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    report_benchmark_exit(proc)


# ------------------------------------------------------------------ preflight
def preflight() -> int:
    import mirage_cli

    if mirage_cli.needs_setup():
        E.warn("environment not ready; running setup first")
        rc = mirage_cli.cmd_setup([])
        if rc != 0:
            return rc
        print()
    checks = doctor.system_checks() + doctor.project_checks()
    groups = [
        ("Python environment", lambda c: c.name in ("Python", "virtualenv", "platform", "Git")),
        ("MIRAGE package", lambda c: c.name == "MIRAGE import"),
        ("API dependencies", lambda c: c.group == "python" and c.name not in ("Python", "virtualenv", "MIRAGE import") and c.name not in ("environment initialises", "deterministic scientific smoke", "record / replay", "trust-boundary smoke")),
        ("Frontend dependencies", lambda c: c.group == "frontend"),
        ("Scientific smoke test", lambda c: c.name in ("environment initialises", "deterministic scientific smoke", "record / replay", "trust-boundary smoke")),
    ]
    bad = [c for c in checks if c.status == "fail"]
    for title, pick in groups:
        members = [c for c in checks if pick(c)]
        if any(c.status == "fail" for c in members):
            E.fail(title)
        else:
            E.ok(title)
    if bad:
        for c in bad:
            print(f"\n  {c.name}: {c.detail}\n    fix: {c.fix or 'run ./mirage doctor'}")
        return 1
    return 0


def stop_stale() -> bool:
    """Orphaned MIRAGE services (supervisor died) are ours to stop. Returns True if a live
    supervisor owns the stack, in which case we leave it alone."""
    if E.owned_pid("supervisor"):
        return True
    for role in ("api", "web"):
        pid = E.owned_pid(role)
        if pid:
            E.warn(f"stopping stale MIRAGE {role} process (pid {pid})")
            E.terminate_group(pid)
        E.remove_pidfile(role)
    return False


def pick_port(preferred: int, role: str, label: str, avoid: set[int]) -> int:
    if preferred not in avoid and E.port_free(preferred):
        return preferred
    pid = E.port_owner_pid(preferred)
    if pid and E.is_mirage_process(pid):
        # A MIRAGE process started by hand (or by an older launcher): ours to stop, but only with consent.
        if sys.stdin.isatty() and input(f"Port {preferred} is held by an untracked MIRAGE {role} process (pid {pid}). Stop it? [y/N] ").strip().lower() == "y":
            E.terminate_group(pid)
            if E.port_free(preferred):
                return preferred
        else:
            E.warn(f"port {preferred} is held by an untracked MIRAGE process (pid {pid}); leaving it running (kill {pid} to free the port)")
    owner = E.port_owner(preferred)
    chosen = E.find_free_port(preferred + 1, avoid=avoid | {preferred})
    E.warn(f"port {preferred} is in use by {owner}; {label} will use {chosen} instead (the other program is left untouched)")
    return chosen


# ------------------------------------------------------------------ main
def main(argv: list[str], *, dev: bool = False) -> int:
    args = parse(argv)
    E.banner("Scientific Campaign Control" + ("  ·  dev mode" if dev else ""))
    print()
    if args.docker:
        return run_docker(args)

    rc = preflight()
    if rc:
        return rc

    if stop_stale():
        rec = E.read_pidfile("web") or {}
        api = E.read_pidfile("api") or {}
        url = cockpit_url(args, rec.get("port", args.frontend_port))
        E.warn(f"MIRAGE is already running (pid {E.owned_pid('supervisor')}).")
        E.info(f"Cockpit: {url}   API: http://localhost:{api.get('port', args.port)}")
        E.info("Run ./mirage stop first to restart with different options.")
        if not args.no_browser and not dev:
            open_browser(url)
        return 0

    api_port = pick_port(args.port, "api", "the API", set())
    web_port = pick_port(args.frontend_port, "web", "the cockpit", {api_port})
    token = secrets.token_urlsafe(18)  # local, per-run; reaches the API and the Vite proxy via env only
    E.RECORDS.mkdir(parents=True, exist_ok=True)

    api = Service(
        "api", "API",
        [str(E.venv_python()), "scripts/serve_api.py", "--host", "127.0.0.1", "--port", str(api_port),
         "--records", str(E.RECORDS), "--scenario", args.scenario, "--scenario-version", args.version,
         "--benchmark-store", str(E.LOCAL / "benchmark-dev" / "binder_campaign" / "privileged"),
         "--cors-origin", f"http://localhost:{web_port}", "--cors-origin", f"http://127.0.0.1:{web_port}",
         "--log-level", "info"],
        E.ROOT, E.project_env({"MIRAGE_EVAL_TOKEN": token}), api_port, "cyan")
    web = Service(
        "web", "WEB",
        [str(E.vite_bin()), "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"],
        E.FRONTEND,
        E.project_env({"MIRAGE_API_PROXY": f"http://127.0.0.1:{api_port}", "MIRAGE_EVAL_TOKEN": token,
                       "VITE_MIRAGE_EVALUATION": "1", "VITE_MIRAGE_BENCHMARKS": "1", "FORCE_COLOR": "0"}),
        web_port, "yellow")
    services = [api, web]

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: stop.set())
    E.write_pidfile("supervisor", os.getpid(), api_port=api_port, web_port=web_port)

    code = 0
    benchmark: subprocess.Popen | None = None
    try:
        print("\nStarting services...")
        echo = dev or args.verbose
        api.start(echo)
        failed = wait_for(lambda: bool((E.http_json(f"http://127.0.0.1:{api_port}/health") or {}).get("status") == "ok"), [api], STARTUP_TIMEOUT)
        if failed:
            show_failure(failed, [api])
            return 1
        benchmark = start_development_benchmark(args.no_benchmark)
        web.start(echo)
        failed = wait_for(lambda: E.http_ok(f"http://127.0.0.1:{web_port}/", contains='id="root"'), services, STARTUP_TIMEOUT)
        if failed:
            show_failure(failed, services if failed == "timeout" else [web])
            return 1
        proxied = wait_for(lambda: bool((E.http_json(f"http://127.0.0.1:{web_port}/api/health") or {}).get("status") == "ok"), services, 15)
        if proxied:
            show_failure("frontend → API proxy", services)
            return 1

        url = cockpit_url(args, web_port)
        print()
        print(E.paint("MIRAGE is running", "green", "bold"))
        print()
        print(f"  Cockpit:     {url}")
        print(f"  API docs:    http://localhost:{api_port}/docs")
        print(f"  Health:      http://localhost:{api_port}/health")
        print()
        print(f"  Scenario:    {args.scenario}   {E.paint('(orchestration metadata; hidden from the policy)', 'dim')}")
        print(f"  Semantics:   {args.version}")
        print(f"  Policy:      {args.policy}")
        print(f"  Seed:        {args.seed}")
        sha = E.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=E.ROOT).stdout.strip()
        print(f"  Commit:      {sha}")
        print(f"  Processes:   api pid {api.proc.pid} · web pid {web.proc.pid} · logs .local/mirage/logs/")
        print()
        if (not dev and not args.no_browser) or (dev and args.open):
            print("Opening browser...")
            if not open_browser(url):
                E.warn(f"could not open a browser automatically; open this URL yourself:\n    {url}")
        print("Ctrl+C to stop")

        while not stop.is_set():
            dead = [s for s in services if not s.alive]
            if dead:
                E.fail(f"{dead[0].label} exited unexpectedly (code {dead[0].proc.returncode})")
                show_failure(dead[0].label, [dead[0]])
                code = 1
                break
            if benchmark is not None and report_benchmark_exit(benchmark):
                benchmark = None
            stop.wait(0.5)
        if stop.is_set():
            print("\nShutting down...")
    finally:
        if benchmark is not None:
            stop_development_benchmark(benchmark)
        for s in reversed(services):
            s.stop()
        E.remove_pidfile("supervisor")
    if stop.is_set():
        E.ok("stopped API and cockpit")
    return code


def cockpit_url(args: argparse.Namespace, web_port: int) -> str:
    q = ["transport=live"]
    if args.seed != DEFAULTS["seed"]:
        q.append(f"seed={args.seed}")
    if args.scenario != DEFAULTS["scenario"]:
        q.append(f"scenario={args.scenario}")
    if args.version != DEFAULTS["version"]:
        q.append(f"semantics={args.version}")
    if args.policy != DEFAULTS["policy"]:
        q.append(f"policy={args.policy}")
    if args.guided:
        q.append("guided=1")
    return f"http://localhost:{web_port}/?" + "&".join(q)


def run_docker(args: argparse.Namespace) -> int:
    compose = None
    if shutil.which("docker") and E.run(["docker", "compose", "version"]).returncode == 0:
        compose = ["docker", "compose"]
    elif shutil.which("docker-compose"):
        compose = ["docker-compose"]
    if compose is None:
        E.fail("docker compose not found. Install Docker, or use the native path: ./mirage demo")
        return 1
    env = {**os.environ, "MIRAGE_SCENARIO": args.scenario, "MIRAGE_SCENARIO_VERSION": args.version,
           "MIRAGE_API_PORT": str(args.port), "MIRAGE_WEB_PORT": str(args.frontend_port),
           "MIRAGE_EVAL_TOKEN": secrets.token_urlsafe(18),
           "MIRAGE_GIT_SHA": E.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=E.ROOT).stdout.strip()}
    url = cockpit_url(args, args.frontend_port)
    print(f"Starting with docker compose (fallback path). Cockpit: {url}\nCtrl+C to stop.\n")
    proc = subprocess.Popen([*compose, "up", "--build"], cwd=E.ROOT, env=env)
    threading.Thread(target=lambda: (wait_for(lambda: E.http_ok(f"http://127.0.0.1:{args.frontend_port}/"), [], 300) is None and not args.no_browser and open_browser(url)), daemon=True).start()
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.send_signal(signal.SIGINT)
        proc.wait()
        subprocess.run([*compose, "down"], cwd=E.ROOT, env=env, check=False)
        return 0
