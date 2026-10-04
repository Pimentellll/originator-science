"""Decision-latency profile for GreedyEIGPolicy (B3).

Measures wall-clock seconds of one ``choose_action`` call (all 7 assays scored, shared
hypothetical sources) over a grid of particle counts and Monte Carlo sample counts, at the
prior and after two observations. Uses the test-only prior from tests/binder_support.py, so
the numbers characterise the algorithm's cost, not any benchmark world.

    PYTHONPATH=src:tests:tests/policies python scripts/profile_greedy_eig.py [--repeats 9] [--json]
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import time

import numpy as np

from binder_support import MODEL, act, make_belief, obs
from policy_helpers import make_actions, make_state

from mirage.core.contracts import ActionType as A
from mirage.policies import GreedyEIGPolicy


def profile(n_particles: int, n_samples: int, stage: str, repeats: int) -> dict:
    belief = make_belief(n_particles, seed=0, conditioned=True, ess_threshold=0.5)
    if stage == "after_2_obs":
        belief.observe(MODEL, act(A.MEASURE_SEC), obs(A.MEASURE_SEC, monomer_fraction=0.55))
        belief.observe(MODEL, act(A.MEASURE_SPR), obs(A.MEASURE_SPR, log_kd=-8.5, log_koff=-2.0))
    policy = GreedyEIGPolicy(MODEL, lambda: belief, seed=0, n_samples=n_samples)
    state, summary, actions = make_state(), belief.summary(), make_actions()
    policy.choose_action(state, summary, actions)  # warm-up (imports, caches)
    times = []
    for r in range(repeats):
        policy.reset(r)
        policy.choose_action(state, summary, actions)
        times.append(policy.last_decision_seconds)
    times.sort()
    return {
        "particles": n_particles,
        "mc_samples": n_samples,
        "stage": stage,
        "median_s": statistics.median(times),
        "p95_s": times[min(len(times) - 1, int(np.ceil(0.95 * len(times))) - 1)],
        "max_s": times[-1],
        "assays_scored": len(policy.last_scores),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=9)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    rows = [
        profile(n, m, stage, args.repeats)
        for stage in ("prior", "after_2_obs")
        for n in (256, 512, 1024, 2048)
        for m in (32, 64, 128)
    ]
    meta = {"python": platform.python_version(), "numpy": np.__version__, "machine": platform.machine(), "processor": platform.processor() or platform.platform(), "timestamp_unix": int(time.time())}
    if args.json:
        print(json.dumps({"meta": meta, "rows": rows}, indent=2))
        return
    print(f"# GreedyEIG decision latency ({meta['python']}, numpy {meta['numpy']}, {meta['machine']})")
    print("| stage | particles | MC samples | median s | p95 s | max s |")
    print("|---|---:|---:|---:|---:|---:|")
    for r in rows:
        print(f"| {r['stage']} | {r['particles']} | {r['mc_samples']} | {r['median_s']:.3f} | {r['p95_s']:.3f} | {r['max_s']:.3f} |")


if __name__ == "__main__":
    main()
