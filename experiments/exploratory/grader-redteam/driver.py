"""Grader red-team driver: run scripted adversaries with the frozen evaluator, then re-score.

Usage (from the repo root):
  PYTHONPATH=src .venv/bin/python experiments/exploratory/grader-redteam/driver.py run --matrix strong
  PYTHONPATH=src .venv/bin/python experiments/exploratory/grader-redteam/driver.py run --matrix dev
  PYTHONPATH=src .venv/bin/python experiments/exploratory/grader-redteam/driver.py frozen
  PYTHONPATH=src .venv/bin/python experiments/exploratory/grader-redteam/driver.py report

Strong-matrix runs keep full records under runs/strong/<agent>/ (runner layout). Dev-block
full records go to .local/grader-redteam/dev/<agent>/; the committed runs/dev/<agent>/ holds
the manifest, the runner's summary.json, results.md and a compact episodes.jsonl.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import rescore
from agents import EDGE_CONTROL, make_agents

from mirage.biology.conditions import Condition
from mirage.config import (
    EpisodeConfig,
    canonical_sha256,
    load_prior,
    sample_episode,
)
from mirage.evaluation import runner
from mirage.evaluation.metrics import wilson
from mirage.evaluation.passive import REFERENCE_SEEDS, build_reference
from mirage.lab.environment import LabEnvironment
from mirage.lab.tools import PROMPT_VERSION, Observation, ToolResponse

ROOT = runner.ROOT
RUNS = HERE / "runs"
DEV_MATRIX = HERE / "dev_matrix.json"
DEV_SCRATCH = ROOT / ".local" / "grader-redteam" / "dev"
FROZEN_RUNS = {
    "C1 Claude Opus 5.5": "20261003-2323_claude_strong",
    "C2 Claude Sonnet 5.5": "20261004-0049_claude_strong",
    "B1 GoodScientist": "20261003-2333_good_scientist_strong",
    "B2 PassiveBayes": "20261003-2333_passive_bayes_strong",
}
SCRIPTED_FROZEN = {
    "B1 GoodScientist": "ref_good_scientist",
    "B2 PassiveBayes": "ref_passive_bayes",
}
DEV_SEEDS = range(1000)


def dev_matrix_spec() -> dict:
    """Seeds 0-999: BP for even seeds, MA for odd seeds (REGISTRATION.md)."""
    return {
        "matrices": {
            "dev": {
                "episodes": [
                    {
                        "seed": s,
                        "condition": (
                            Condition.BIOLOGICAL_PLATEAU
                            if s % 2 == 0
                            else Condition.MEASUREMENT_ARTIFACT
                        ).value,
                    }
                    for s in DEV_SEEDS
                ]
            }
        }
    }


def matrix_path(matrix: str) -> Path:
    if matrix == "strong":
        return runner.MATRIX
    if matrix == "dev":
        return DEV_MATRIX
    raise ValueError(f"unknown matrix {matrix!r}")


def other(condition: Condition) -> Condition:
    return (
        Condition.MEASUREMENT_ARTIFACT
        if condition is Condition.BIOLOGICAL_PLATEAU
        else Condition.BIOLOGICAL_PLATEAU
    )


class TwinSession:
    """Real passive data; every measure_od is answered by the matched twin world."""

    def __init__(self, real: LabEnvironment, twin: LabEnvironment) -> None:
        self._real, self._twin = real, twin

    def observation(self) -> Observation:
        return self._real.observation()

    def call(self, tool: str, args: dict[str, Any]) -> ToolResponse:
        return (self._twin if tool == "measure_od" else self._real).call(tool, args)

    @property
    def finished(self) -> bool:
        return self._real.finished


def twin_label(cfg: EpisodeConfig, agent: Any, prior) -> str | None:
    """The agent's label when all its measurements come from the same seed's other world."""
    real = LabEnvironment(cfg)
    twin = LabEnvironment(sample_episode(prior, cfg.seed, other(cfg.condition)))
    agent.run(TwinSession(real, twin))
    return real.diagnosis.diagnosis if real.diagnosis is not None else None


def setup():
    prior = load_prior(runner.SCENARIO)
    dset = runner.frozen_dset(prior, runner.GATE0_SUMMARY)
    classifier = build_reference(prior, REFERENCE_SEEDS)
    agents = make_agents(
        classifier, rescore.tau(EDGE_CONTROL["dilution_factor"], prior)
    )
    return prior, dset, agents


def write_results_md(run_dir: Path, agent_id: str) -> None:
    s = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    lines = [
        f"# {agent_id} on `{s['matrix']}` (exploratory, grader red-team)",
        "",
        "Produced from summary.json (written by `mirage.evaluation.runner.summarize`).",
        "",
        "| Block | n | M1 | M2 | M3 | M4 mean | Q1 | Brier |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for block in ("overall", "BIOLOGICAL_PLATEAU", "MEASUREMENT_ARTIFACT"):
        b = s["metrics"]["primary"][block]
        cells = [block, str(b["n"])]
        for m in ("M1", "M2", "M3"):
            lo, hi = b[m]["wilson95"]
            cells.append(f"{b[m]['k']}/{b['n']} [{lo:.2f}, {hi:.2f}]")
        cells += [
            f"{b['M4']['mean']:.2f}",
            f"{b['Q1']:.3f}",
            "n/a" if b["O1"] is None else f"{b['O1']:.4f}",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    runner.write_atomic(run_dir / "results.md", "\n".join(lines) + "\n")


def run_block(agent_id: str, agent: Any, matrix: str, prior, dset) -> Path:
    """Run one agent on one matrix with the frozen run_episode / summarize; return committed dir."""
    mpath = matrix_path(matrix)
    cfgs = [
        sample_episode(prior, seed, c) for seed, c in runner.load_matrix(mpath, matrix)
    ]
    committed = RUNS / matrix / agent_id
    run_dir = committed if matrix == "strong" else DEV_SCRATCH / agent_id
    for d in {committed, run_dir}:
        if d.exists():
            raise FileExistsError(f"{d} already exists; runs are never overwritten")
    manifest = {
        "run_id": f"grader-redteam_{agent_id}_{matrix}",
        "agent": agent_id,
        "matrix": matrix,
        "matrix_sha256": runner.file_sha256(mpath),
        "scenario_sha256": canonical_sha256(prior),
        "gate0_summary_sha256": runner.file_sha256(runner.GATE0_SUMMARY),
        "diagnostic_action_set": dset.model_dump(mode="json"),
        "prompt_version": PROMPT_VERSION,
        "n_episodes": len(cfgs),
        "versions": runner.versions(),
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "exploratory": "grader-redteam; scripted adversary; not a benchmark result",
    }
    runner.write_atomic(run_dir / "manifest.json", runner.dumps(manifest))
    rows = []
    for cfg in cfgs:
        res = runner.run_episode(cfg, agent, dset, {"run_id": manifest["run_id"]})
        runner.write_atomic(
            run_dir / "episodes" / f"{cfg.episode_id}.json",
            runner.dumps(res.model_dump(mode="json")),
        )
        rows.append(rescore.compact(res, prior, twin_label(cfg, agent, prior)))
    runner.summarize(run_dir)
    if run_dir != committed:
        committed.mkdir(parents=True)
        for name in ("manifest.json", "summary.json"):
            shutil.copy2(run_dir / name, committed / name)
    write_results_md(committed, agent_id)
    runner.write_atomic(
        committed / "episodes.jsonl",
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows),
    )
    return committed


def frozen(prior, agents) -> Path:
    """Re-score the committed frozen runs (read-only) into frozen_rescore/<label>.jsonl."""
    out = HERE / "frozen_rescore"
    for label, run_id in FROZEN_RUNS.items():
        rs = runner.load_results(ROOT / "experiments" / "results" / run_id)
        rows = []
        for r in rs:
            twin = None
            if label in SCRIPTED_FROZEN:
                twin = twin_label(r.episode, agents[SCRIPTED_FROZEN[label]], prior)
            rows.append(rescore.compact(r, prior, twin))
        runner.write_atomic(
            out / f"{run_id}.jsonl",
            "".join(json.dumps(x, sort_keys=True) + "\n" for x in rows),
        )
    return out


def read_rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def kn(rows: list[dict], key) -> dict:
    vals = [key(r) for r in rows]
    if any(v is None for v in vals):
        return {"k": None, "n": len(rows)}
    k, n = sum(bool(v) for v in vals), len(vals)
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "wilson95": [lo, hi]}


def table_rows(rows: list[dict]) -> dict:
    """Frozen metrics and proposed-rule metrics for one agent's rows (primary statuses only)."""
    rows = [r for r in rows if r["status"] in ("DIAGNOSED", "NO_DIAGNOSIS")]
    briers = [r["scores"]["brier"] for r in rows if r["scores"]["brier"] is not None]
    return {
        "M1": kn(rows, lambda r: r["scores"]["correct"]),
        "M2": kn(rows, lambda r: r["scores"]["diagnostic_control"]),
        "M3": kn(rows, lambda r: r["scores"]["justified"]),
        "Q1": kn(rows, lambda r: r["scores"]["reconstruction_adequate"]),
        "brier": sum(briers) / len(briers) if briers else None,
        "M3_P1": kn(rows, lambda r: r["justified_p1"]),
        "M3_P2": kn(rows, lambda r: r["justified_p2"]),
        "M3_P4": kn(rows, lambda r: r["justified_p4"]),
        **{
            f"Q1_P3_{t:.2f}": kn(rows, lambda r, t=t: r[f"q1_p3_{t:.2f}"])
            for t in rescore.P3_TOLERANCES
        },
        "label_p_incoherent": sum(
            1
            for r in rows
            if r["diagnosis"] is not None
            and (r["p"] > 0.5) != (r["diagnosis"] == rescore.ABOVE)
        ),
        "M4_mean": sum(r["scores"]["cost_units"] for r in rows) / len(rows),
    }


def report() -> Path:
    """tables.json with every agent x matrix and frozen re-score (feeds RESULT.md and the figure)."""
    out: dict[str, Any] = {"strong": {}, "dev": {}, "frozen": {}}
    for matrix in ("strong", "dev"):
        for d in sorted((RUNS / matrix).iterdir()):
            out[matrix][d.name] = table_rows(read_rows(d / "episodes.jsonl"))
    for label, run_id in FROZEN_RUNS.items():
        out["frozen"][label] = table_rows(
            read_rows(HERE / "frozen_rescore" / f"{run_id}.jsonl")
        )
    path = HERE / "tables.json"
    runner.write_atomic(path, runner.dumps(out))
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="grader-redteam")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--matrix", choices=("strong", "dev"), required=True)
    r.add_argument("--agents", nargs="*", default=None)
    sub.add_parser("frozen")
    sub.add_parser("report")
    sub.add_parser("dev-matrix")
    args = ap.parse_args(argv)
    if args.cmd == "dev-matrix":
        runner.write_atomic(DEV_MATRIX, runner.dumps(dev_matrix_spec()))
        print(DEV_MATRIX)
        return 0
    if args.cmd == "report":
        print(report())
        return 0
    prior, dset, agents = setup()
    if args.cmd == "frozen":
        print(frozen(prior, agents))
        return 0
    for agent_id in args.agents or list(agents):
        print(
            run_block(agent_id, agents[agent_id], args.matrix, prior, dset), flush=True
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
