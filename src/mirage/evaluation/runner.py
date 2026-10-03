"""HIDDEN: episode orchestration, persistence and summaries (DESIGN §11, §18).

Usage:
  python -m mirage.evaluation.runner run --agent good_scientist --matrix minimal [--out DIR]
  python -m mirage.evaluation.runner run --agent claude --matrix minimal [--model ID]
      [--resume RUN_ID] [--matrix-file PATH]
  python -m mirage.evaluation.runner summarize RUN_DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import tempfile
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from mirage.agents.scripted import GoodScientist, PassiveBayesAgent
from mirage.biology.conditions import ABBREVIATION, Condition
from mirage.config import ScenarioPrior, canonical_sha256, load_prior, sample_episode
from mirage.evaluation.metrics import (
    SCHEMA_VERSION,
    AgentInfo,
    DiagnosticActionSet,
    EpisodeResult,
    aggregate,
    audit_measurements,
    load_diagnostic_action_set,
    score_episode,
)
from mirage.evaluation.passive import REFERENCE_SEEDS, build_reference
from mirage.lab.environment import LabEnvironment
from mirage.lab.tools import PROMPT_VERSION

ROOT = Path(__file__).resolve().parents[3]
SCENARIO = ROOT / "experiments" / "configs" / "scenario_v1.json"
MATRIX = ROOT / "experiments" / "configs" / "eval_matrix_v1.json"
GATE0_SUMMARY = ROOT / "experiments" / "results" / "gate0" / "summary.json"
SCRATCH = ROOT / ".local" / "runs"
SUMMARY_VERSION = "run-summary-v1"
AGENTS = ("good_scientist", "passive_bayes", "claude")
API_KEY_ENV = "ANTHROPIC_API_KEY"


def dumps(obj: Any) -> str:
    """DESIGN §18 serialisation."""
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def versions() -> dict[str, str]:
    out = {"python": platform.python_version()}
    for pkg in ("mirage", "numpy", "pydantic", "anthropic"):
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = "not installed"
    return out


def load_matrix(path: Path, name: str) -> list[tuple[int, Condition]]:
    spec = json.loads(path.read_text(encoding="utf-8"))["matrices"][name]
    if "episodes" in spec:
        return [(int(e["seed"]), Condition(e["condition"])) for e in spec["episodes"]]
    lo, hi = spec["seed_range"]
    return [(s, Condition(c)) for c in spec["conditions"] for s in range(lo, hi + 1)]


def frozen_dset(prior: ScenarioPrior, gate0_summary: Path) -> DiagnosticActionSet:
    """D_diag from the Gate 0 summary; refuses to start on a scenario hash mismatch (T-031)."""
    if not gate0_summary.exists():
        raise FileNotFoundError(
            f"{gate0_summary} not found: Gate 0 must pass before scored runs (DESIGN §17)"
        )
    try:
        return load_diagnostic_action_set(gate0_summary, canonical_sha256(prior))
    except ValueError as err:
        raise ValueError(f"hash mismatch: refusing to start ({err})") from err


def make_agent(name: str, prior: ScenarioPrior, reference_seeds=REFERENCE_SEEDS, *,
               client: Any | None = None, model: str | None = None):
    if name == "claude":
        from mirage.agents.claude import ClaudeAgent, DEFAULT_MODEL

        # Never falls back to another model; ``client`` is injectable for tests only.
        return ClaudeAgent(client, model=model or DEFAULT_MODEL)
    if name in ("good_scientist", "passive_bayes") and model is not None:
        raise ValueError("--model is only supported with --agent claude")
    if name == "good_scientist":
        return GoodScientist()
    if name == "passive_bayes":
        return PassiveBayesAgent(build_reference(prior, reference_seeds))
    raise ValueError(f"unknown agent {name!r}; expected one of {AGENTS}")


def is_llm(agent: Any) -> bool:
    return getattr(agent, "kind", "scripted") == "llm"


def agent_info(agent: Any) -> AgentInfo:
    if not is_llm(agent):
        return AgentInfo(name=agent.name, kind="scripted", model=None, effort=None,
                         prompt_version=None, prompt_sha256=None, sdk_version=None)
    return AgentInfo(name=agent.name, kind="llm", model=agent.model, effort=agent.effort,
                     prompt_version=agent.prompt_version, prompt_sha256=agent.prompt_sha256,
                     sdk_version=agent.sdk_version)


def run_episode(prior: ScenarioPrior, seed: int, condition: Condition, agent: Any,
                dset: DiagnosticActionSet, run_meta: dict[str, Any]) -> EpisodeResult:
    cfg = sample_episode(prior, seed, condition)
    env = LabEnvironment(cfg)
    started = _now()
    agent.run(env.session())  # scripted agents propagate errors: a bug is a test failure
    llm = is_llm(agent)
    if not env.finished:  # finish() raises on an already-final episode (PR #36)
        env.finish((agent.outcome if llm else None) or "NO_DIAGNOSIS")
    audit = audit_measurements(cfg, env.events, dset)
    return EpisodeResult(
        schema_version=SCHEMA_VERSION,
        episode=cfg,
        agent=agent_info(agent),
        passive=env.passive,
        events=env.events,
        diagnosis=env.diagnosis,
        status=env.status,
        audit=audit,
        scores=score_episode(cfg, env.events, env.diagnosis, audit),
        llm_transcript=list(agent.transcript) if llm else None,
        versions=versions(),
        run_meta={**run_meta, "started_at": started, "finished_at": _now()},
    )


def run(agent_name: str, matrix_name: str, out_root: Path, *, scenario: Path = SCENARIO,
        matrix: Path = MATRIX, gate0_summary: Path = GATE0_SUMMARY, run_id: str | None = None,
        reference_seeds=REFERENCE_SEEDS, client: Any | None = None, model: str | None = None,
        resume: bool = False) -> Path:
    """Run every matrix episode; write manifest.json, episodes/*.json, then summary.json.

    ``resume`` continues an interrupted run in place: the manifest must match exactly and
    finished episode files are skipped, never rewritten.
    """
    if model is not None and agent_name != "claude":
        raise ValueError("--model is only supported with --agent claude")
    prior = load_prior(scenario)
    dset = frozen_dset(prior, gate0_summary)
    episodes = load_matrix(matrix, matrix_name)
    if agent_name == "claude" and client is None and not os.environ.get(API_KEY_ENV):
        raise ValueError(f"{API_KEY_ENV} is not set; refusing to start a paid run without it")
    agent = make_agent(agent_name, prior, reference_seeds, client=client, model=model)
    if resume and not run_id:
        raise ValueError("--resume needs the RUN_ID of the run to continue")
    run_id = run_id or f"{datetime.now(timezone.utc):%Y%m%d-%H%M}_{agent_name}_{matrix_name}"
    run_dir = out_root / run_id
    if run_dir.exists() and not resume:
        raise FileExistsError(f"{run_dir} already exists; runs are never overwritten")
    if resume and not (run_dir / "manifest.json").exists():
        raise FileNotFoundError(f"{run_dir} has no manifest.json to resume")
    manifest = {
        "run_id": run_id, "agent": agent_name, "matrix": matrix_name,
        "matrix_sha256": file_sha256(matrix), "scenario_sha256": canonical_sha256(prior),
        "gate0_summary_sha256": file_sha256(gate0_summary), "diagnostic_action_set":
            dset.model_dump(mode="json"), "prompt_version": PROMPT_VERSION,
        "n_episodes": len(episodes), "versions": versions(), "created_at": _now(),
    }
    if is_llm(agent):
        manifest |= {"model": agent.model, "effort": agent.effort,
                     "prompt_sha256": agent.prompt_sha256}
    manifest_path = run_dir / "manifest.json"
    if resume:
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        changed = sorted(k for k in manifest if k not in ("created_at", "versions")
                         and manifest[k] != old.get(k))
        if changed:
            raise ValueError(f"cannot resume {run_id}: manifest differs in {', '.join(changed)}")
        base_manifest = old
    else:
        write_atomic(manifest_path, dumps(manifest))
        base_manifest = manifest
    meta = {"run_id": run_id}
    for seed, cond in episodes:
        episode_id = f"s{seed}-{ABBREVIATION[cond]}"
        episode_path = run_dir / "episodes" / f"{episode_id}.json"
        attempt1_path = run_dir / "reruns" / f"{episode_id}.attempt1.json"
        if resume and episode_path.exists():
            continue  # atomic writes: a file is a finished episode, never a partial one
        rerun_in_progress = resume and agent_name == "claude" and attempt1_path.exists()
        res = run_episode(prior, seed, cond, agent, dset, meta)
        if agent_name == "claude" and res.status == "API_FAILURE" and not rerun_in_progress:
            write_atomic(attempt1_path, dumps(res.model_dump(mode="json")))
            res = run_episode(prior, seed, cond, agent, dset, meta)
        write_atomic(run_dir / "episodes" / f"{res.episode.episode_id}.json",
                     dumps(res.model_dump(mode="json")))
    if agent_name == "claude":
        reruns = {
            path.name.removesuffix(".attempt1.json"): f"reruns/{path.name}"
            for path in sorted((run_dir / "reruns").glob("*.attempt1.json"))
        }
        write_atomic(manifest_path, dumps({**base_manifest, "reruns": reruns}))
    summarize(run_dir)
    return run_dir


def load_results(run_dir: Path) -> list[EpisodeResult]:
    files = sorted((run_dir / "episodes").glob("*.json"))
    return [EpisodeResult.model_validate_json(f.read_text(encoding="utf-8")) for f in files]


def summarize(run_dir: Path) -> Path:
    """Recompute summary.json from the episode files only; no wall-clock fields (T-023)."""
    results = load_results(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    summary = {
        "schema_version": SUMMARY_VERSION,
        "run_id": manifest["run_id"], "agent": manifest["agent"], "matrix": manifest["matrix"],
        "matrix_sha256": manifest["matrix_sha256"],
        "scenario_sha256": manifest["scenario_sha256"],
        "n_episodes": len(results),
        "episode_ids": [r.episode.episode_id for r in results],
        "metrics": aggregate(results),
    }
    path = run_dir / "summary.json"
    write_atomic(path, dumps(summary))
    return path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mirage-runner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--agent", choices=AGENTS, required=True)
    r.add_argument("--matrix", required=True)
    r.add_argument("--model", default=None, help="LLM agent only; never substituted")
    r.add_argument("--matrix-file", type=Path, default=MATRIX)
    r.add_argument("--resume", metavar="RUN_ID", help="continue an interrupted run in --out")
    r.add_argument("--out", type=Path, default=SCRATCH)
    r.add_argument("--gate0-summary", type=Path, default=GATE0_SUMMARY)
    s = sub.add_parser("summarize")
    s.add_argument("run_dir", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "run":
        try:
            path = run(args.agent, args.matrix, args.out, gate0_summary=args.gate0_summary,
                       matrix=args.matrix_file, model=args.model, run_id=args.resume,
                       resume=bool(args.resume))
        except (FileNotFoundError, ValueError, FileExistsError) as err:
            print(f"runner: {err}", file=sys.stderr)
            return 2
        print(path)
    else:
        print(summarize(args.run_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
