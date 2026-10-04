"""Write the machine-readable V2 spec + seed manifest and the hash lock. Run once, then commit.

    python scripts/freeze_rescue_v2.py [--lock]

Without --lock only spec.json and seed_manifest.json are (re)written; --lock additionally writes
PREREGISTRATION.json. After the preregistration commit, never run it again for V2.
"""

import argparse
import json
from pathlib import Path

from mirage.evaluation.campaign import rescue_v2 as r

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / r.PREREG_DIR


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    spec = r.spec_dict()
    (OUT / "spec.json").write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    seeds = {
        "spec_version": r.SPEC_VERSION,
        "development": r.SEEDS["development"],
        "held_out": r.SEEDS["held_out"],
        "train_reserved_inclusive": r.SEEDS["train_reserved_inclusive"],
        "v1_development_not_reused": r.V1_SEEDS["development"],
        "v1_held_out_not_reused": r.V1_SEEDS["held_out"],
        "rules": [
            "development seeds: policy tuning allowed; never reported as results",
            "held-out seeds: evaluation only; all 50 are used for every archetype and stratum; no extension, no replacement, no dropping",
            "train range: learned policies only, resources sampled from the same strata distribution",
            "the four sets are pairwise disjoint",
        ],
        "worlds": {"archetypes": len(spec["archetypes"]), "strata": 3, "seeds": len(r.SEEDS["held_out"]),
                    "worlds_per_stratum": spec["worlds_per_stratum"], "episodes_per_policy": spec["episodes_per_policy"]},
    }
    (OUT / "seed_manifest.json").write_text(json.dumps(seeds, indent=2, sort_keys=True) + "\n")
    if args.lock:
        lock = {
            "status": "LOCKED before any V2 policy evaluation",
            "lock": r.compute_lock(ROOT),
            "feasibility_properties_of_the_sampler": {
                s: {
                    "funnel_affordable_fraction": round(r.funnel_affordable_fraction(s), 4),
                    "justified_select_structurally_possible": {k: round(v, 4) for k, v in r.select_justifiable_fraction(s).items()},
                }
                for s in r.STRATUM_ORDER
            },
            "structural_minimum_cost_to_justify": r.minimal_justified_costs(),
        }
        (OUT / "PREREGISTRATION.json").write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
