"""Public-safe system metadata: build info, policy catalogue, scenario catalogue, self-checks.

Everything here is orchestration/system information for the human running a demo. None of it
is policy input and none of it carries simulator or evaluator state. Keys deliberately avoid
the trust-boundary vocabulary so the API's leak guard stays armed on these routes.
"""

from __future__ import annotations

import os
import platform
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict

import mirage

_REPO = Path(__file__).resolve().parents[3]


class _Meta(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class VersionDTO(_Meta):
    mirage_version: str
    git_sha: str
    git_dirty: bool | None
    commit_date: str | None
    api_version: str
    contract_version: str
    scenario_semantics_default: str
    scenario_semantics_available: tuple[str, ...]
    python_version: str


class PolicyInfoDTO(_Meta):
    name: str
    display_name: str
    kind: str
    available: bool
    description: str
    reason: str | None = None


class ScenarioInfoDTO(_Meta):
    id: str
    title: str
    summary: str
    cli_name: str


class CheckDTO(_Meta):
    name: str
    status: str  # pass | fail | skip
    detail: str


class DiagnosticsDTO(_Meta):
    status: str  # ok | degraded
    checks: tuple[CheckDTO, ...]
    git_sha: str
    scenario_semantics_default: str
    note: str


@dataclass(frozen=True)
class SystemCatalogue:
    """Everything the system routes serve besides the live episode state."""

    policies: tuple[PolicyInfoDTO, ...] = ()
    scenarios: tuple[ScenarioInfoDTO, ...] = ()
    semantics_default: str = "unspecified"
    semantics_available: tuple[str, ...] = ()
    selfcheck: "SelfCheck | None" = None


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=_REPO, capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


@lru_cache(maxsize=1)
def git_info() -> tuple[str, bool | None, str | None]:
    """(short sha, dirty flag, commit date). ``MIRAGE_GIT_SHA`` overrides for containers/exports.

    Never raises and never reports a filesystem path.
    """
    sha = os.environ.get("MIRAGE_GIT_SHA") or _git("rev-parse", "--short=12", "HEAD") or "unknown"
    status = _git("status", "--porcelain", "--untracked-files=no")
    dirty = None if status is None else bool(status)
    return sha, dirty, _git("log", "-1", "--format=%cI")


def code_version() -> str:
    """Compact reproducibility tag stored in every public record (<= 64 chars)."""
    sha, dirty, _ = git_info()
    return f"{sha}-dirty" if dirty else sha


def version_info(*, api_version: str, contract_version: str, semantics_default: str, semantics_available: tuple[str, ...]) -> VersionDTO:
    sha, dirty, date = git_info()
    return VersionDTO(
        mirage_version=mirage.__version__,
        git_sha=sha,
        git_dirty=dirty,
        commit_date=date,
        api_version=api_version,
        contract_version=contract_version,
        scenario_semantics_default=semantics_default,
        scenario_semantics_available=semantics_available,
        python_version=platform.python_version(),
    )


class SelfCheck:
    """Lazily-computed, cached diagnostics. The callable returns a tuple of ``CheckDTO``."""

    def __init__(self, run: Callable[[], tuple[CheckDTO, ...]]) -> None:
        self._run = run
        self._lock = threading.Lock()
        self._cached: tuple[CheckDTO, ...] | None = None

    def get(self, *, refresh: bool = False) -> tuple[CheckDTO, ...]:
        with self._lock:
            if refresh or self._cached is None:
                self._cached = self._run()
            return self._cached
