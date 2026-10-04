"""``./mirage doctor``: environment diagnostics with exact fixes. Standard library only."""

from __future__ import annotations

import json
import shutil
import sys

import mirage_env as E
from mirage_env import Check

NODE_FIX = (
    "install Node 22 LTS, e.g.  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash"
    "  &&  exec bash  &&  nvm install 22   (macOS: brew install node@22)"
)


def system_checks() -> list[Check]:
    out: list[Check] = []
    plat = E.detect_platform()
    out.append(Check("platform", "pass" if plat.supported else "fail", plat.label,
                     "" if plat.supported else "use WSL2 Ubuntu 24.04 (see docs/DEVELOPER_SETUP.md)", "system"))

    git = E.version_of(["git", "--version"]) if shutil.which("git") else None
    out.append(Check("Git", "pass" if git else "fail", git or "not found",
                     "" if git else "sudo apt install git   (macOS: xcode-select --install)", "system"))

    vpy = E.venv_python()
    if vpy.exists():
        v = E.version_of([str(vpy), "--version"]) or "?"
        good = E.parse_version(v)[:2] >= E.MIN_PYTHON
        out.append(Check("Python", "pass" if good else "fail", f"{v} (.venv)",
                         "" if good else "delete .venv and run: ./mirage setup   (needs Python >= 3.11; uv can fetch one)", "python"))
        out.append(Check("virtualenv", "pass", ".venv", "", "python"))
    else:
        found = E.find_system_python()
        out.append(Check("Python", "pass" if found else "warn",
                         f"{found[1]} (system; .venv not created yet)" if found else "no Python >= 3.11 found on PATH",
                         "" if found else "install Python 3.11+ (sudo apt install python3 python3-venv) or let ./mirage setup fetch one via uv", "python"))
        out.append(Check("virtualenv", "fail", ".venv missing", "run: ./mirage setup", "python"))

    node = E.version_of(["node", "--version"]) if shutil.which("node") else None
    if node is None:
        out.append(Check("Node", "fail", "not found", NODE_FIX, "frontend"))
    else:
        good = E.node_ok(node)
        out.append(Check("Node", "pass" if good else "fail", node,
                         "" if good else f"Node {node} is too old for Vite 8 (needs 20.19+ or 22.12+). " + NODE_FIX, "frontend"))
    npm = E.version_of(["npm", "--version"]) if shutil.which("npm") else None
    out.append(Check("npm", "pass" if npm else "fail", npm or "not found", "" if npm else "npm ships with Node: " + NODE_FIX, "frontend"))
    ready = E.frontend_deps_ready()
    out.append(Check("frontend deps", "pass" if ready else "fail",
                     "frontend/node_modules" if ready else ("out of date with package-lock.json" if E.vite_bin().exists() else "not installed"),
                     "" if ready else "run: ./mirage setup", "frontend"))
    return out


def project_checks() -> list[Check]:
    """Delegates to the virtualenv so imports are tested where the services will run."""
    vpy = E.venv_python()
    if not vpy.exists():
        return [Check("MIRAGE import", "skip", "needs .venv", "run: ./mirage setup", "python")]
    try:
        proc = E.run([str(vpy), str(E.ROOT / "scripts" / "doctor_checks.py")], cwd=E.ROOT, env=E.project_env(), timeout=240)
        rows = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except Exception as exc:  # noqa: BLE001 - doctor must report, not crash
        return [Check("project checks", "fail", f"{type(exc).__name__}: {exc}"[:200], "run: ./mirage setup", "python")]
    return [Check(r["name"], r["status"], r["detail"], r["fix"], "python") for r in rows]


def port_checks(api_port: int = E.DEFAULT_API_PORT, web_port: int = E.DEFAULT_WEB_PORT) -> list[Check]:
    out: list[Check] = []
    for role, port, label in (("api", api_port, "API"), ("web", web_port, "cockpit")):
        if E.port_free(port):
            out.append(Check(f"port {port}", "pass", f"available ({label})", "", "ports"))
            continue
        mine = E.owned_pid(role)
        other = E.port_owner_pid(port)
        if mine:
            out.append(Check(f"port {port}", "pass", f"in use by this MIRAGE ({label}, pid {mine})", "", "ports"))
        elif other and E.is_mirage_process(other):
            out.append(Check(f"port {port}", "warn", f"in use by an untracked MIRAGE {label} process (pid {other}); MIRAGE will pick another port",
                             f"stop it with: kill {other}", "ports"))
        else:
            out.append(Check(f"port {port}", "warn", f"in use by {E.port_owner(port)}; MIRAGE will pick another port",
                             f"free it, or pass --port / --frontend-port to ./mirage demo", "ports"))
    return out


def service_checks(api_port: int) -> list[Check]:
    rec = E.read_pidfile("api")
    port = (rec or {}).get("port", api_port) if E.owned_pid("api") else api_port
    health = E.http_json(f"http://127.0.0.1:{port}/health")
    if health and health.get("status") == "ok":
        mine = "" if E.owned_pid("api") else " (not started by ./mirage)"
        return [Check("backend health", "pass", f"http://127.0.0.1:{port}/health{mine}", "", "services")]
    return [Check("backend health", "skip", "API not running (./mirage demo starts it)", "", "services")]


def collect(api_port: int = E.DEFAULT_API_PORT, web_port: int = E.DEFAULT_WEB_PORT, *, include_project: bool = True) -> list[Check]:
    checks = system_checks()
    if include_project:
        checks += project_checks()
    return checks + port_checks(api_port, web_port) + service_checks(api_port)


def render(checks: list[Check]) -> int:
    print("MIRAGE Doctor")
    print(E.paint("─" * 40, "dim"))
    print()
    width = max(len(c.name) for c in checks) + 2
    tag = {"pass": E.paint("[PASS]", "green"), "fail": E.paint("[FAIL]", "red"), "warn": E.paint("[WARN]", "yellow"), "skip": E.paint("[SKIP]", "dim")}
    for c in checks:
        print(f"{tag[c.status]} {c.name.ljust(width)}{c.detail}")
    print()
    failed = [c for c in checks if c.status == "fail"]
    if not failed:
        print(E.paint("READY TO RUN MIRAGE", "green", "bold"))
        return 0
    print(E.paint(f"NOT READY: {len(failed)} problem{'s' if len(failed) != 1 else ''}", "red", "bold"))
    for c in failed:
        print(f"\n  {E.paint(c.name, 'bold')}: {c.detail}")
        if c.fix:
            print(f"    fix: {c.fix}")
    return 1


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    checks = collect()
    failed = any(c.status == "fail" for c in checks)
    if as_json:
        json.dump({"ready": not failed, "checks": [c.as_dict() for c in checks]}, sys.stdout, indent=2)
        print()
        return 1 if failed else 0
    return render(checks)
