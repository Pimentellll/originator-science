#!/usr/bin/env python3
"""Project-side doctor checks, run INSIDE the project virtualenv by ``./mirage doctor``.

Prints one JSON list of ``{name, status, detail, fix}`` to stdout. Never raises: a failing
import or check is reported, not thrown. Reuses the same self-checks as ``GET /diagnostics``.
"""
import importlib
import importlib.metadata as md
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX_SETUP = "run: ./mirage setup"
out = []


def add(name, status, detail="", fix=""):
    out.append({"name": name, "status": status, "detail": detail, "fix": fix})


def dist_version(name):
    try:
        return md.version(name)
    except md.PackageNotFoundError:
        return None


try:
    import mirage

    location = Path(mirage.__file__).resolve()
    inside = ROOT / "src" in location.parents
    add("MIRAGE import", "pass" if inside else "fail",
        f"mirage {mirage.__version__}" if inside else f"imports a different checkout: {location.parents[1]}",
        "" if inside else "run: ./mirage setup   (re-points the editable install at this checkout)")
except Exception as exc:  # noqa: BLE001
    add("MIRAGE import", "fail", f"{type(exc).__name__}: {exc}", FIX_SETUP)

for label, module, dist in (
    ("FastAPI", "fastapi", "fastapi"),
    ("uvicorn", "uvicorn", "uvicorn"),
    ("NumPy", "numpy", "numpy"),
    ("pydantic", "pydantic", "pydantic"),
    ("httpx", "httpx", "httpx"),
    ("Gymnasium", "gymnasium", "gymnasium"),
    ("Stable Baselines3", "stable_baselines3", "stable-baselines3"),
    ("SB3-Contrib", "sb3_contrib", "sb3-contrib"),
    ("pytest", "pytest", "pytest"),
):
    try:
        importlib.import_module(module)
        add(label, "pass", dist_version(dist) or "")
    except Exception as exc:  # noqa: BLE001
        add(label, "fail", f"{type(exc).__name__}: {exc}".splitlines()[0][:120], FIX_SETUP)

try:
    from mirage.api.meta import git_info  # noqa: F401
    from mirage.environments.binder import BinderWorldMode
    from mirage.environments.binder.scenarios import BinderScenarioVersion
    from mirage.integration.catalogue import run_selfchecks

    labels = {
        "environment": "environment initialises",
        "deterministic_smoke": "deterministic scientific smoke",
        "record_replay": "record / replay",
        "leak_guard": "trust-boundary smoke",
    }
    for check in run_selfchecks(BinderWorldMode.COMPOUND_FAILURE, BinderScenarioVersion.SEMANTICS_V2):
        add(labels.get(check.name, check.name), "pass" if check.status == "pass" else "fail", check.detail,
            "" if check.status == "pass" else "run: ./mirage test --quick   and read the first failure")
except Exception as exc:  # noqa: BLE001
    add("deterministic scientific smoke", "fail", f"{type(exc).__name__}: {exc}".splitlines()[0][:160], FIX_SETUP)

json.dump(out, sys.stdout)
