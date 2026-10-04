"""Domain randomization for campaign-level RL training (F2, F3).

A ``WorldConfig`` is a pure function of ``(seed, stage)``: the same seed always yields the
same world mode and the same lab conditions, so any policy can be evaluated on identical
worlds. The config is training-side construction data. It is never part of an
observation, and the world mode is never exposed to the policy.

Seed splits are disjoint integer ranges asserted at import time.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from mirage.environments.binder import BinderWorldMode

NOMINAL_BUDGET = 12.0
NOMINAL_SAMPLE = 8.0

TRAIN_SEED_START, TRAIN_SEED_COUNT = 10_000_000, 1_000_000
VAL_SEED_START, VAL_SEED_COUNT = 15_000_000, 200
HELD_OUT_SEED_START, HELD_OUT_SEED_COUNT = 20_000_000, 300

TRAIN_SEEDS = range(TRAIN_SEED_START, TRAIN_SEED_START + TRAIN_SEED_COUNT)
VAL_SEEDS = range(VAL_SEED_START, VAL_SEED_START + VAL_SEED_COUNT)
HELD_OUT_SEEDS = range(HELD_OUT_SEED_START, HELD_OUT_SEED_START + HELD_OUT_SEED_COUNT)


def _disjoint(*ranges: range) -> bool:
    ordered = sorted(ranges, key=lambda r: r.start)
    return all(a.stop <= b.start for a, b in zip(ordered, ordered[1:]))


assert _disjoint(TRAIN_SEEDS, VAL_SEEDS, HELD_OUT_SEEDS), "train/val/held-out seed ranges overlap"

_M = BinderWorldMode

# Curriculum (F3): mode weights per stage. Stage 4 is the full mixture.
CURRICULUM: dict[int, dict[BinderWorldMode, float]] = {
    1: {_M.SINGLE_FAILURE: 1.0},
    2: {_M.SINGLE_FAILURE: 0.5, _M.COMPOUND_FAILURE: 0.5},
    3: {_M.SINGLE_FAILURE: 0.25, _M.COMPOUND_FAILURE: 0.25, _M.ASSAY_FAILURE: 0.25, _M.MODEL_FAILURE: 0.25},
    4: {mode: 0.2 for mode in BinderWorldMode},
}
FULL_STAGE = 4


@dataclass(frozen=True)
class WorldConfig:
    """Lab conditions and world class for one episode (training-side construction data)."""

    world_mode: BinderWorldMode
    budget: float = NOMINAL_BUDGET
    sample: float = NOMINAL_SAMPLE
    cost_scale: float = 1.0
    spr_cost_scale: float = 1.0
    initial_spr_health: float = 1.0
    assay_noise_scale: float = 1.0
    redesign_effect_scale: float = 1.0

    @property
    def is_nominal(self) -> bool:
        return (self.budget, self.sample, self.cost_scale, self.spr_cost_scale, self.initial_spr_health,
                self.assay_noise_scale, self.redesign_effect_scale) == (NOMINAL_BUDGET, NOMINAL_SAMPLE, 1.0, 1.0, 1.0, 1.0, 1.0)


def sample_world_config(seed: int, stage: int = FULL_STAGE, *, randomize: bool = True, nominal_fraction: float = 0.25) -> WorldConfig:
    """Deterministic config for ``seed``.

    ``randomize=False`` keeps the benchmark's nominal lab (budget 12, sample 8, unit costs,
    full SPR health) and only varies the world mode. With ``randomize=True`` a fraction
    ``nominal_fraction`` of seeds is also nominal, so the evaluation condition lies inside
    the training distribution.
    """
    rng = np.random.default_rng([int(seed), 7919])
    weights = CURRICULUM[stage]
    modes = list(weights)
    probs = np.array([weights[m] for m in modes], dtype=float)
    mode = modes[int(rng.choice(len(modes), p=probs / probs.sum()))]
    nominal_draw = rng.random()  # drawn unconditionally so the stream is identical in both branches
    if not randomize or nominal_draw < nominal_fraction:
        return WorldConfig(world_mode=mode)
    return WorldConfig(
        world_mode=mode,
        budget=float(rng.uniform(8.0, 16.0)),
        sample=float(rng.uniform(5.0, 10.0)),
        cost_scale=float(np.exp(rng.uniform(np.log(0.7), np.log(1.4)))),
        spr_cost_scale=float(np.exp(rng.uniform(np.log(0.8), np.log(1.5)))),
        initial_spr_health=float(1.0 if rng.random() < 0.6 else rng.uniform(0.6, 1.0)),
        assay_noise_scale=float(rng.uniform(0.85, 1.25)),
        redesign_effect_scale=float(rng.uniform(0.7, 1.3)),
    )
