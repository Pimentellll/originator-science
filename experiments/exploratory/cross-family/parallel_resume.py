"""Finish an interrupted Y2 run with several worker processes (same model, settings, episodes).

Each worker runs a disjoint shard of the episodes that have no record yet, using the same
per-episode logic as ``runner.run`` (one re-run after API_FAILURE, atomic writes). Afterwards
``driver.py run --config Y2 --matrix strong --resume RUN_ID`` skips every finished episode and
writes the manifest re-run index and summary.json exactly as a sequential run would.

Usage: python parallel_resume.py RUN_ID SHARD N_SHARDS
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("exp_cross_family_driver", HERE / "driver.py")
assert spec is not None and spec.loader is not None
driver = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = driver
spec.loader.exec_module(driver)
runner = driver.runner


def main(run_id: str, shard: int, n_shards: int, config_id: str = "Y2") -> None:
    model, effort = driver.CONFIGS[config_id]
    provider = driver.PROVIDERS[config_id]
    run_dir = driver.STRONG_OUT_ROOT / run_id
    if not (run_dir / "manifest.json").exists():
        raise FileNotFoundError(f"{run_dir} has no manifest.json")
    metered = driver.MeteredClient(
        provider["client"](),
        run_dir=run_dir,
        ledger_path=provider["ledger"],
        run_id=run_id,
        config=config_id,
        matrix="strong",
        cap=provider["cap"],
    )
    agent = provider["agent"](metered, model=model, effort=effort)
    prior = runner.load_prior(runner.SCENARIO)
    dset = runner.frozen_dset(prior, runner.GATE0_SUMMARY)
    cfgs = [
        runner.sample_episode(prior, seed, condition)
        for seed, condition in runner.load_matrix(driver.STRONG_MATRIX, "strong")
    ]
    todo = [c for c in cfgs if not (run_dir / "episodes" / f"{c.episode_id}.json").exists()]
    meta = {"run_id": run_id}
    for cfg in todo[shard::n_shards]:
        episode_path = run_dir / "episodes" / f"{cfg.episode_id}.json"
        attempt1_path = run_dir / "reruns" / f"{cfg.episode_id}.attempt1.json"
        if episode_path.exists():
            continue
        rerun_in_progress = attempt1_path.exists()
        res = runner.run_episode(cfg, agent, dset, meta)
        if res.status == "API_FAILURE" and not rerun_in_progress:
            runner.write_atomic(attempt1_path, runner.dumps(res.model_dump(mode="json")))
            res = runner.run_episode(cfg, agent, dset, meta)
        runner.write_atomic(episode_path, runner.dumps(res.model_dump(mode="json")))
        print(f"shard {shard}: {cfg.episode_id} {res.status}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
