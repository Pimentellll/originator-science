"""Shared helpers for the ``./mirage`` launcher. Standard library only, so it runs under any
Python 3.9+ before the project virtualenv exists.

Everything project-specific lives in ``.venv`` and ``frontend/node_modules``; runtime state
lives in ``.local/mirage`` (git-ignored). Nothing here touches global Python packages.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
VENV = ROOT / ".venv"
LOCAL = ROOT / ".local"
RUNTIME = LOCAL / "mirage"
PIDS = RUNTIME / "pids"
LOGS = RUNTIME / "logs"
STAMPS = RUNTIME / "stamps"
RECORDS = LOCAL / "mirage-api"

DEFAULT_API_PORT = 8000
DEFAULT_WEB_PORT = 5173
MIN_PYTHON = (3, 11)
# Vite 8 supports Node 20.19+ and 22.12+.
MIN_NODE = ((20, 19), (22, 12))

# Dependency groups installed by `./mirage setup`. pyproject.toml is the single source of truth;
# the README's manual fallback installs exactly this.
PROJECT_EXTRAS = "dev,rl"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
UV_INSTALL_URL = "https://astral.sh/uv/install.sh"


# ------------------------------------------------------------------ terminal output
def _color_ok() -> bool:
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"


_C = {"red": "31", "green": "32", "yellow": "33", "blue": "34", "dim": "2", "bold": "1", "cyan": "36"}


def paint(text: str, *styles: str) -> str:
    if not _color_ok():
        return text
    return "".join(f"\033[{_C[s]}m" for s in styles) + text + "\033[0m"


def banner(subtitle: str = "Scientific Campaign Control") -> None:
    width = 46
    print(paint("╭" + "─" * width + "╮", "dim"))
    print(paint("│", "dim") + " " + paint("MIRAGE".ljust(width - 1), "bold") + paint("│", "dim"))
    print(paint("│", "dim") + " " + subtitle.ljust(width - 1) + paint("│", "dim"))
    print(paint("╰" + "─" * width + "╯", "dim"))


def ok(msg: str) -> None:
    print(f"{paint('✓', 'green')} {msg}")


def warn(msg: str) -> None:
    print(f"{paint('!', 'yellow')} {msg}")


def fail(msg: str) -> None:
    print(f"{paint('✗', 'red')} {msg}", file=sys.stderr)


def info(msg: str) -> None:
    print(f"  {msg}")


# ------------------------------------------------------------------ platform
@dataclass(frozen=True)
class Platform:
    system: str  # linux | macos | windows | other
    wsl: bool
    supported: bool
    label: str


def detect_platform() -> Platform:
    sysname = platform.system()
    if sysname == "Linux":
        wsl = False
        try:
            wsl = "microsoft" in Path("/proc/version").read_text().lower()
        except OSError:
            pass
        distro = ""
        try:
            for line in Path("/etc/os-release").read_text().splitlines():
                if line.startswith("PRETTY_NAME="):
                    distro = line.split("=", 1)[1].strip('"')
        except OSError:
            pass
        label = (distro or "Linux") + (" (WSL2)" if wsl else "")
        return Platform("linux", wsl, True, label)
    if sysname == "Darwin":
        return Platform("macos", False, True, f"macOS {platform.mac_ver()[0]} (secondary support)")
    if sysname == "Windows":
        return Platform("windows", False, False, "Windows (native)")
    return Platform("other", False, False, sysname or "unknown")


WINDOWS_MESSAGE = """\
MIRAGE does not support native Windows. Use WSL2 with Ubuntu 24.04:

  1. In an administrator PowerShell:   wsl --install -d Ubuntu-24.04
  2. Open the Ubuntu terminal (not PowerShell or cmd), then:
       git clone https://github.com/Pimentellll/originator-science.git
       cd originator-science
       ./mirage demo

Keep the checkout inside the Linux filesystem (~/...), not /mnt/c/..., for speed."""


# ------------------------------------------------------------------ processes
def run(argv: list[str], *, cwd: Path | None = None, env: dict | None = None, timeout: float | None = None, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, env=env, timeout=timeout, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.STDOUT if capture else None, check=False)


def version_of(argv: list[str]) -> str | None:
    try:
        out = run(argv, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    m = re.search(r"\d+(?:\.\d+)+", out.stdout or "")
    return m.group(0) if m else (out.stdout or "").strip()[:40] or None


def parse_version(text: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", text)[:3])


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def project_env(extra: dict | None = None) -> dict:
    """Environment for project subprocesses: venv first on PATH, src importable, no leakage of a
    stray caller virtualenv."""
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONHOME", None)
    env["PATH"] = f"{VENV / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    env["PYTHONPATH"] = str(ROOT / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONUNBUFFERED"] = "1"
    env.update(extra or {})
    return env


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return not _is_zombie(pid)


def _is_zombie(pid: int) -> bool:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] == "Z"
    except (OSError, IndexError):
        return False


def cmdline_of(pid: int) -> str:
    """Full command line of a process, or '' when unknown."""
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
    except OSError:
        pass
    try:
        out = run(["ps", "-o", "command=", "-p", str(pid)], timeout=5)
        return (out.stdout or "").strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


# ------------------------------------------------------------------ pid registry
ROLE_MARKERS = {"api": "serve_api.py", "web": "vite", "supervisor": "mirage_cli.py"}


def pidfile(role: str) -> Path:
    return PIDS / f"{role}.json"


def write_pidfile(role: str, pid: int, **extra) -> None:
    PIDS.mkdir(parents=True, exist_ok=True)
    data = {"role": role, "pid": pid, "root": str(ROOT), "started": time.time(), **extra}
    pidfile(role).write_text(json.dumps(data, indent=2))


def read_pidfile(role: str) -> dict | None:
    try:
        return json.loads(pidfile(role).read_text())
    except (OSError, ValueError):
        return None


def remove_pidfile(role: str) -> None:
    try:
        pidfile(role).unlink()
    except OSError:
        pass


def owned_pid(role: str) -> int | None:
    """PID of a live MIRAGE-owned process for ``role``, verified against its command line.

    A stale pidfile whose pid was recycled by an unrelated program is never trusted."""
    rec = read_pidfile(role)
    if not rec or rec.get("root") != str(ROOT):
        return None
    pid = int(rec["pid"])
    if not pid_alive(pid):
        return None
    cmd = cmdline_of(pid)
    if ROLE_MARKERS[role] in cmd and (str(ROOT) in cmd or role == "web" or role == "supervisor"):
        return pid
    return None


def terminate_process(pid: int, *, grace: float = 12.0) -> bool:
    """SIGTERM one process (not its group: the supervisor shares a group with the user's shell),
    giving it time to stop its own children; SIGKILL only if it ignores that."""
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 2.0)):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return True
        deadline = time.time() + wait
        while time.time() < deadline:
            if not pid_alive(pid):
                return True
            time.sleep(0.1)
    return not pid_alive(pid)


def terminate_group(pid: int, *, grace: float = 6.0) -> bool:
    """SIGTERM the process group (children included), then SIGKILL stragglers. True when gone."""
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return True
    own = os.getpgrp()
    targets = [pgid] if pgid != own else []
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for g in targets:
            try:
                os.killpg(g, sig)
            except (ProcessLookupError, PermissionError):
                pass
        if not targets:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        deadline = time.time() + (grace if sig == signal.SIGTERM else 2.0)
        while time.time() < deadline:
            if not pid_alive(pid):
                return True
            time.sleep(0.1)
    return not pid_alive(pid)


# ------------------------------------------------------------------ ports
def port_free(port: int) -> bool:
    """Free on loopback v4/v6 and the wildcard, i.e. nothing a browser could hit instead."""
    for family, addr in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET, "0.0.0.0"), (socket.AF_INET6, "::1")):
        try:
            s = socket.socket(family, socket.SOCK_STREAM)
        except OSError:
            continue  # family unavailable on this host
        try:
            # SO_REUSEADDR: a port in TIME_WAIT after a clean shutdown is free (uvicorn and Vite
            # bind the same way); only a live listener makes bind fail.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((addr, port))
        except OSError as exc:
            if family == socket.AF_INET6 and exc.errno in (97, 99, 10049):  # no IPv6 here
                continue
            return False
        finally:
            s.close()
    return True


def port_owner_pid(port: int) -> int | None:
    """PID listening on ``port`` (own processes only on most systems), best effort."""
    for argv in (["ss", "-ltnpH", f"sport = :{port}"], ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fp"]):
        if shutil.which(argv[0]):
            try:
                out = run(argv, timeout=5).stdout or ""
            except (OSError, subprocess.SubprocessError):
                continue
            m = re.search(r"pid=(\d+)", out) or re.search(r"^p(\d+)", out, re.M)
            if m:
                return int(m.group(1))
    return None


def port_owner(port: int) -> str:
    """Human description of whatever listens on ``port``."""
    pid = port_owner_pid(port)
    if pid is None:
        return "another program"
    cmd = cmdline_of(pid)
    name = Path(cmd.split(" ")[0]).name if cmd else "process"
    return f"{name} (pid {pid})"


def is_mirage_process(pid: int) -> bool:
    """A process that looks like this checkout's API or cockpit, started outside the launcher."""
    cmd = cmdline_of(pid)
    return str(ROOT) in cmd and ("serve_api.py" in cmd or "vite" in cmd)


def find_free_port(preferred: int, *, avoid: set[int] = frozenset(), span: int = 40) -> int:
    for p in range(preferred, preferred + span):
        if p not in avoid and port_free(p):
            return p
    raise RuntimeError(f"no free port found in {preferred}-{preferred + span - 1}")


def http_ok(url: str, *, timeout: float = 2.0, contains: str | None = None) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - loopback only
            body = resp.read(65536).decode(errors="replace") if contains else ""
            return 200 <= resp.status < 400 and (contains is None or contains in body)
    except (OSError, urllib.error.URLError, ValueError):
        return False


def http_json(url: str, *, timeout: float = 3.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - loopback only
            return json.loads(resp.read().decode())
    except (OSError, urllib.error.URLError, ValueError):
        return None


# ------------------------------------------------------------------ tooling discovery
def find_uv() -> str | None:
    found = shutil.which("uv")
    if found:
        return found
    for cand in (Path.home() / ".local/bin/uv", Path.home() / ".cargo/bin/uv"):
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


def find_system_python() -> tuple[str, str] | None:
    """A system interpreter >= 3.11 (path, version), preferring newer ones."""
    for name in ("python3.13", "python3.12", "python3.11", "python3", "python"):
        path = shutil.which(name)
        if not path:
            continue
        v = version_of([path, "--version"])
        if v and parse_version(v)[:2] >= MIN_PYTHON:
            return path, v
    return None


def node_ok(version: str) -> bool:
    v = parse_version(version)[:2]
    return any(v[0] == lo[0] and v >= lo for lo in MIN_NODE) or v[0] > MIN_NODE[-1][0]


def file_digest(*paths: Path) -> str:
    h = hashlib.sha256()
    for p in paths:
        try:
            h.update(p.read_bytes())
        except OSError:
            h.update(b"<missing>")
    return h.hexdigest()[:16]


def read_stamp(name: str) -> dict:
    try:
        return json.loads((STAMPS / f"{name}.json").read_text())
    except (OSError, ValueError):
        return {}


def write_stamp(name: str, data: dict) -> None:
    STAMPS.mkdir(parents=True, exist_ok=True)
    (STAMPS / f"{name}.json").write_text(json.dumps(data, indent=2))


def python_stamp_key() -> dict:
    return {"pyproject": file_digest(ROOT / "pyproject.toml"), "extras": PROJECT_EXTRAS, "root": str(ROOT)}


def frontend_stamp_key() -> dict:
    return {"lock": file_digest(FRONTEND / "package-lock.json", FRONTEND / "package.json")}


def vite_bin() -> Path:
    return FRONTEND / "node_modules" / ".bin" / "vite"


def frontend_deps_ready() -> bool:
    """Installed and consistent with package.json/package-lock.json.

    A matching stamp (written by ``./mirage setup``) is the fast path; otherwise ``npm ls`` is
    the authority, so a checkout installed by hand with ``npm ci`` is recognised too."""
    if not vite_bin().exists():
        return False
    if read_stamp("frontend").get("key") == frontend_stamp_key():
        return True
    if shutil.which("npm") and run(["npm", "ls", "--depth=0", "--silent"], cwd=FRONTEND, timeout=60).returncode == 0:
        write_stamp("frontend", {"key": frontend_stamp_key(), "via": "npm ls"})
        return True
    return False


def tail(path: Path, lines: int = 25) -> str:
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])
    except OSError:
        return "(no log)"


@dataclass
class Check:
    name: str
    status: str  # pass | fail | warn | skip
    detail: str = ""
    fix: str = ""
    group: str = ""
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "detail": self.detail, "fix": self.fix, "group": self.group}
