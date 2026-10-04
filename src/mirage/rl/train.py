"""Train MaskablePPO on the randomized Binder BioPOMDP (F1-F4).

    python -m mirage.rl.train --timesteps 400000 --n-envs 12 --out runs/f1

Writes ``train_log.jsonl`` (rolling training statistics), ``val_log.jsonl`` (periodic
validation on VAL seeds), ``config.json`` and checkpoints. The held-out seeds are never
touched here; use ``mirage.rl.report`` after training.
"""

from __future__ import annotations

import os

# Belief updates are tiny matrix ops; per-process BLAS threads only oversubscribe the cores.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse
import hashlib
import json
import time
from collections import deque
from pathlib import Path

import numpy as np
from sb3_contrib import MaskablePPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv

from mirage.rl.evaluate import rollout_policy, summarise
from mirage.rl.gym_env import BinderCampaignEnv
from mirage.rl.observation import ACTION_ORDER, OBS_DIM
from mirage.rl.policy import PPOPolicy
from mirage.rl.randomization import HELD_OUT_SEEDS, TRAIN_SEEDS, VAL_SEEDS
from mirage.rl.reward import RewardConfig


def _append(path: Path, row: dict) -> None:
    with path.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


class CampaignStats(BaseCallback):
    """Rolling statistics over finished training episodes (training-utility only)."""

    def __init__(self, path: Path, every: int, window: int = 600) -> None:
        super().__init__()
        self.path, self.every, self.window = path, every, window
        self.recent: deque[dict] = deque(maxlen=window)
        self.terms: deque[dict[str, float]] = deque(maxlen=window)  # per-episode sums of reward terms
        self._open: dict[int, dict[str, float]] = {}
        self._next = every
        self.t0 = time.time()
        self.episodes_path = path.with_name("episodes.jsonl")
        self.seeds: set[int] = set()

    def _on_step(self) -> bool:
        for i, (info, done) in enumerate(zip(self.locals["infos"], self.locals["dones"])):
            acc = self._open.setdefault(i, {})
            for k, v in info.get("reward_terms", {}).items():
                acc[k] = acc.get(k, 0.0) + v
            if done and "episode_summary" in info:
                summary = info["episode_summary"]
                self.recent.append(summary)
                self.terms.append(self._open.pop(i, {}))
                self.seeds.add(summary["episode_seed"])
                _append(self.episodes_path, {k: summary[k] for k in ("episode_seed", "world_mode", "decision", "return", "steps", "terminal_utility")} | {"timesteps": self.num_timesteps})
        if self.num_timesteps >= self._next and self.recent:
            self._next += self.every
            names = sorted({k for ep in self.terms for k in ep})
            row = {"timesteps": self.num_timesteps, "environment_interactions": self.num_timesteps, "wall_seconds": time.time() - self.t0,
                   "reward_decomposition_per_episode": {k: float(np.mean([ep.get(k, 0.0) for ep in self.terms])) for k in names},
                   **summarise(list(self.recent))}
            _append(self.path, row)
            for k in ("return_mean", "terminal_utility_mean", "steps_mean", "budget_spent_mean"):
                self.logger.record(f"campaign/{k}", row[k])
        return True


class Validation(BaseCallback):
    """Periodic deterministic evaluation on VAL seeds; keeps the best checkpoint by mean return."""

    def __init__(self, out: Path, every: int, n_val: int, particles: int) -> None:
        super().__init__()
        self.out, self.every, self.n_val, self.particles = out, every, n_val, particles
        self.best, self._next = -np.inf, every

    def _on_step(self) -> bool:
        if self.num_timesteps >= self._next:
            self._next += self.every
            self._run()
        return True

    def _run(self) -> None:
        policy = PPOPolicy(model=self.model)
        seeds = list(VAL_SEEDS)[: self.n_val]
        nominal = summarise(rollout_policy(policy, seeds, randomize=False, particles=self.particles))
        randomized = summarise(rollout_policy(policy, seeds, randomize=True, particles=self.particles))
        _append(self.out / "val_log.jsonl", {"timesteps": self.num_timesteps, "nominal": nominal, "randomized": randomized})
        score = 0.5 * (nominal["return_mean"] + randomized["return_mean"])
        self.logger.record("val/return_mean", score)
        self.model.save(self.out / "latest")
        self.model.save(self.out / f"ckpt_{self.num_timesteps:08d}")
        if score > self.best:
            self.best = score
            self.model.save(self.out / "best")


class Curriculum(BaseCallback):
    """Switch the training world mixture at given timesteps: ``"0:1,150000:2,300000:3,450000:4"``."""

    def __init__(self, schedule: str) -> None:
        super().__init__()
        self.schedule = sorted((int(a), int(b)) for a, b in (p.split(":") for p in schedule.split(",")))
        self.applied = -1

    def _on_step(self) -> bool:
        stage = max((s for t, s in self.schedule if self.num_timesteps >= t), default=self.schedule[0][1])
        if stage != self.applied:
            self.training_env.env_method("set_stage", stage)
            self.applied = stage
        return True


def make_env_fn(rank: int, stage: int, particles: int, reward: RewardConfig):
    def _init():
        env = BinderCampaignEnv(TRAIN_SEEDS, stage=stage, randomize=True, particles=particles, reward=reward)
        env.reset(seed=1000 + rank)
        return env
    return _init


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--timesteps", type=int, default=400_000)
    p.add_argument("--n-envs", type=int, default=12)
    p.add_argument("--out", type=Path, default=Path("runs/f1"))
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--particles", type=int, default=256)
    p.add_argument("--n-steps", type=int, default=256)
    p.add_argument("--batch-size", type=int, default=768)
    p.add_argument("--n-epochs", type=int, default=8)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--gamma", type=float, default=0.99)
    p.add_argument("--ent-coef", type=float, default=0.01)
    p.add_argument("--net", type=int, nargs="+", default=[128, 128])
    p.add_argument("--abstain-value", type=float, default=RewardConfig.abstain_value)
    p.add_argument("--lambda-info", type=float, default=RewardConfig.lambda_info)
    p.add_argument("--curriculum", type=str, default="", help='e.g. "0:1,150000:2,300000:3,450000:4"; empty = full mixture throughout')
    p.add_argument("--eval-every", type=int, default=50_000)
    p.add_argument("--n-val", type=int, default=60)
    p.add_argument("--log-every", type=int, default=10_000)
    p.add_argument("--dummy-vec", action="store_true", help="in-process vec env (debugging)")
    args = p.parse_args(argv)

    if args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir())):
        p.error(f"--out already exists and is not empty: {args.out}")
    args.out.mkdir(parents=True, exist_ok=True)
    import torch

    torch.set_num_threads(2)
    reward = RewardConfig(abstain_value=args.abstain_value, lambda_info=args.lambda_info)
    start_stage = 4 if not args.curriculum else min(int(s.split(":")[1]) for s in args.curriculum.split(","))
    fns = [make_env_fn(i, start_stage, args.particles, reward) for i in range(args.n_envs)]
    vec = (DummyVecEnv if args.dummy_vec else SubprocVecEnv)(fns)
    model = MaskablePPO(
        "MlpPolicy", vec, learning_rate=args.lr, n_steps=args.n_steps, batch_size=args.batch_size, n_epochs=args.n_epochs,
        gamma=args.gamma, gae_lambda=0.95, clip_range=0.2, ent_coef=args.ent_coef, seed=args.seed, device="cpu",
        policy_kwargs={"net_arch": {"pi": list(args.net), "vf": list(args.net)}}, verbose=0,
    )
    (args.out / "config.json").write_text(json.dumps({
        "args": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "reward": reward.as_dict(), "obs_dim": OBS_DIM, "actions": [a.value for a in ACTION_ORDER],
        "train_seed_range": [TRAIN_SEEDS.start, TRAIN_SEEDS.stop], "val_seed_range": [VAL_SEEDS.start, VAL_SEEDS.stop],
    }, indent=2))
    callbacks = [CampaignStats(args.out / "train_log.jsonl", args.log_every), Validation(args.out, args.eval_every, args.n_val, args.particles)]
    if args.curriculum:
        callbacks.append(Curriculum(args.curriculum))
    t0 = time.time()
    model.learn(total_timesteps=args.timesteps, callback=callbacks, progress_bar=False)
    model.save(args.out / "final")
    stats = callbacks[0]
    ordered = sorted(stats.seeds)
    (args.out / "wall_time.json").write_text(json.dumps({"environment_interactions": int(model.num_timesteps), "wall_seconds": time.time() - t0}))
    (args.out / "seed_manifest.json").write_text(json.dumps({
        "train_seed_range": [TRAIN_SEEDS.start, TRAIN_SEEDS.stop],
        "validation_seed_range": [VAL_SEEDS.start, VAL_SEEDS.stop],
        "own_heldout_seed_range": [HELD_OUT_SEEDS.start, HELD_OUT_SEEDS.stop],
        "exclusion_rule": "Benchmark/evaluator held-out seeds MUST lie outside the training range; verify against sampled_train_seeds.",
        "training_episodes_completed": int(len(open(stats.episodes_path).readlines())),
        "unique_training_seeds_sampled": len(ordered),
        "sampled_train_seeds_sha256": hashlib.sha256(",".join(map(str, ordered)).encode()).hexdigest(),
        "sampled_train_seeds_file": "sampled_train_seeds.txt",
        "validation_seeds_used_for_checkpoint_selection": [VAL_SEEDS.start, VAL_SEEDS.start + args.n_val],
    }, indent=2))
    (args.out / "sampled_train_seeds.txt").write_text("\n".join(map(str, ordered)) + "\n")
    vec.close()


if __name__ == "__main__":
    main()
