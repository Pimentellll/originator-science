"""Run the real Binder campaign benchmark on held-out seeds and write machine-readable results.

    python scripts/run_binder_benchmark.py --per-archetype 50 --out results

Writes (under --out):
    binder_campaign_benchmark.json          frontend-facing aggregates (no per-episode truth)
    binder_campaign/public/*.jsonl          every episode's public trace (replayable offline)
    binder_campaign/privileged/...          per-episode evaluations + summaries (EVALUATOR-ONLY)
    binder_campaign/showcase/...            aggregation_kinetic_defect replays for every policy

Results are exactly what the evaluator computed from the episodes; nothing is filled in.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from mirage.evaluation.campaign.aggregate import EvaluationStore
from mirage.evaluation.campaign.binder_benchmark import (
    BenchmarkConfig,
    export_showcase_replays,
    np_seed_range,
    result_document,
    run_binder_benchmark,
)
from mirage.evaluation.campaign.harness import SeedSplit
from mirage.provenance import PublicRecordStore

# Disjoint, fixed seed sets. Only held-out is reported.
SPLIT = SeedSplit(development=np_seed_range(1000, 50), held_out=np_seed_range(50000, 100))


def git_version() -> str:
    def run(*args: str) -> str:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()

    sha = run("rev-parse", "--short", "HEAD")
    return sha + ("-dirty" if run("status", "--porcelain", "--untracked-files=no") else "")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-archetype", type=int, default=50)
    parser.add_argument("--split", choices=("development", "held_out"), default="held_out")
    parser.add_argument("--out", type=Path, default=Path("results"))
    parser.add_argument("--particles", type=int, default=512)
    parser.add_argument("--eig-samples", type=int, default=64)
    parser.add_argument("--benchmark-id", default="binder-campaign-v1")
    args = parser.parse_args()

    config = BenchmarkConfig(n_particles=args.particles, eig_samples=args.eig_samples)
    root = args.out / "binder_campaign"
    started = time.time()
    run = run_binder_benchmark(
        benchmark_id=args.benchmark_id,
        split=SPLIT,
        split_name=args.split,
        per_archetype=args.per_archetype,
        config=config,
        code_version=git_version(),
        record_store=PublicRecordStore(root / "public"),
        evaluation_store=EvaluationStore(root / "privileged"),
    )
    replay_paths, showcase_seed = export_showcase_replays(run, root / "showcase")
    document = result_document(run, config, replay_paths=replay_paths)
    document["run"] = {"episodes": len(run.evaluations), "wall_seconds": round(time.time() - started, 1), "showcase_seed": showcase_seed}
    target = args.out / "binder_campaign_benchmark.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(f"wrote {target} ({len(run.evaluations)} episodes, {document['run']['wall_seconds']} s)")


if __name__ == "__main__":
    main()
