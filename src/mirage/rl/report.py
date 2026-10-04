"""One-shot report for a FROZEN checkpoint: learning curves + held-out training-utility sanity check.

    python -m mirage.rl.report --run runs/F1_final --checkpoint best

Run once, after the checkpoint is frozen. Numbers are training utility on this package's own
held-out seed range, a monitoring check and not the scientific benchmark: no correct-vs-justified
scoring, and the benchmark's held-out seeds are never used here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mirage.core import ActionType
from mirage.policies import FixedPipelinePolicy, GreedyEIGPolicy, RandomPolicy
from mirage.policies.base import ScientificPolicy
from mirage.rl.belief import BeliefTracker
from mirage.rl.evaluate import rollout_policy, summarise
from mirage.rl.policy import PPOPolicy
from mirage.rl.randomization import HELD_OUT_SEEDS


class AlwaysAbstain(ScientificPolicy):
    """Degenerate reference: the exploit the reward is designed not to pay for."""

    name = "always_abstain"

    def choose_action(self, state, belief, available_actions):
        return next(a for a in available_actions if a.action_type == ActionType.ABSTAIN)


def plot_curves(run: Path, out: Path) -> None:
    rows = [json.loads(line) for line in (run / "train_log.jsonl").read_text().splitlines()]
    t = [r["timesteps"] for r in rows]
    fig, ax = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    ax[0, 0].plot(t, [r["return_mean"] for r in rows], label="episode return")
    ax[0, 0].plot(t, [r["terminal_utility_mean"] for r in rows], label="terminal utility")
    ax[0, 0].set(title="Training reward (rolling 600 episodes)", xlabel="environment interactions")
    ax[0, 0].legend()
    ax[0, 1].plot(t, [r["steps_mean"] for r in rows], label="non-terminal steps")
    ax[0, 1].plot(t, [r["budget_spent_mean"] for r in rows], label="budget spent")
    ax[0, 1].plot(t, [r["redesigns_mean"] for r in rows], label="redesigns")
    ax[0, 1].set(title="Resource use", xlabel="environment interactions")
    ax[0, 1].legend()
    for d in ("ABSTAIN", "REJECT", "SELECT", "MODEL_INVALID"):
        ax[1, 0].plot(t, [r["decision_distribution"].get(d, 0.0) for r in rows], label=d)
    ax[1, 0].set(title="Terminal decision distribution", xlabel="environment interactions")
    ax[1, 0].legend()
    terms = sorted(rows[-1].get("reward_decomposition_per_episode", {}))
    for k in terms:
        ax[1, 1].plot(t, [r.get("reward_decomposition_per_episode", {}).get(k, 0.0) for r in rows], label=k)
    ax[1, 1].set(title="Reward decomposition (per episode)", xlabel="environment interactions")
    ax[1, 1].legend(fontsize=7)
    fig.savefig(out, dpi=130)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--checkpoint", default="best")
    p.add_argument("--n-heldout", type=int, default=len(HELD_OUT_SEEDS))
    p.add_argument("--particles", type=int, default=256)
    args = p.parse_args()

    ckpt = args.run / f"{args.checkpoint}.zip"
    seeds = list(HELD_OUT_SEEDS)[: args.n_heldout]
    result = {
        "checkpoint": str(ckpt), "checkpoint_sha256": hashlib.sha256(ckpt.read_bytes()).hexdigest(),
        "heldout_seed_range": [seeds[0], seeds[-1] + 1], "n_heldout": len(seeds),
        "note": "Training utility on this package's own held-out seeds; NOT a scientific evaluation.",
    }
    ppo = PPOPolicy(ckpt)
    result["ppo_nominal_lab"] = summarise(rollout_policy(ppo, seeds, randomize=False, particles=args.particles))
    result["ppo_randomized_lab"] = summarise(rollout_policy(PPOPolicy(ckpt), seeds, randomize=True, particles=args.particles))

    holder: dict = {}
    attach = lambda env: holder.update(env=env)  # noqa: E731
    greedy = GreedyEIGPolicy(BeliefTracker(0).model, lambda: holder["env"].tracker.belief, seed=0, n_samples=32)
    result["reference_policies_nominal_lab"] = {
        "always_abstain": summarise(rollout_policy(AlwaysAbstain(), seeds, randomize=False, particles=args.particles)),
        "random_nonterminal": summarise(rollout_policy(RandomPolicy(seed=0, allow_terminal=False), seeds, randomize=False, particles=args.particles)),
        "fixed_pipeline": summarise(rollout_policy(FixedPipelinePolicy(), seeds, randomize=False, particles=args.particles)),
        "greedy_eig": summarise(rollout_policy(greedy, seeds, randomize=False, particles=args.particles, belief_source_factory=attach)),
    }
    (args.run / "report_heldout_training_utility.json").write_text(json.dumps(result, indent=2))
    plot_curves(args.run, args.run / "learning_curves.png")
    print(json.dumps({k: (v["return_mean"], v["terminal_utility_mean"]) for k, v in
                      {"ppo_nominal": result["ppo_nominal_lab"], "ppo_randomized": result["ppo_randomized_lab"],
                       **{f"ref_{k}": v for k, v in result["reference_policies_nominal_lab"].items()}}.items()}, indent=1))


if __name__ == "__main__":
    main()
