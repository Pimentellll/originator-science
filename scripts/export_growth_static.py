"""Export growth benchmark API responses as static JSON files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mirage.ui import api


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def export_growth_static(results_root: str | Path, output_root: str | Path) -> None:
    results = Path(results_root)
    output = Path(output_root)
    runs = api.list_runs(results)
    _write_json(output / "runs.json", runs)

    for entry in runs:
        run_id = entry["run_id"]
        run = api.get_run(results, run_id)
        _write_json(output / "runs" / f"{run_id}.json", run)
        for episode in run["episodes"]:
            episode_id = episode["episode_id"]
            _write_json(
                output / "runs" / run_id / "episodes" / f"{episode_id}.json",
                api.get_episode(results, run_id, episode_id),
            )

    _write_json(output / "grid-strong.json", api.get_grid(results, "strong"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("experiments/results"))
    parser.add_argument("--out", type=Path, default=Path("frontend/public/growth-data"))
    args = parser.parse_args()
    export_growth_static(args.results, args.out)


if __name__ == "__main__":
    main()
