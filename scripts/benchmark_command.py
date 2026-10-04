"""Command construction for the development-split benchmark."""

from __future__ import annotations

import mirage_env as E


def development_benchmark_argv() -> list[str]:
    out = E.LOCAL / "benchmark-dev"
    return [
        str(E.venv_python()),
        "scripts/run_binder_benchmark.py",
        "--split",
        "development",
        "--per-archetype",
        "2",
        "--out",
        str(out),
        "--benchmark-id",
        "binder-campaign-dev",
    ]
