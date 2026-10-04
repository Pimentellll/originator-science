"""Export the finished BASELINE V1 run (read-only; never reruns or overwrites the run)."""

import argparse
from pathlib import Path

from mirage.evaluation.campaign.baseline_export import export_baseline
from run_binder_benchmark import SPLIT

TRAIN_RESERVED = (100_000, 199_999)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=Path("results"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    written = export_baseline(
        results_dir=args.results,
        out_dir=args.out,
        seed_split={"development": SPLIT.development, "held_out": SPLIT.held_out},
        reserved_train_seeds=TRAIN_RESERVED,
    )
    for name, path in sorted(written.items()):
        print(f"{name:20} {path}")


if __name__ == "__main__":
    main()
