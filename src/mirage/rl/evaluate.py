"""Run any ScientificPolicy on the training environment for monitoring and sanity checks.

Numbers produced here are TRAINING UTILITY (the reward-side signal), not scientific
evaluation: no correct-vs-justified scoring, no evidence checks. Independent evaluation
belongs to the privileged benchmark evaluator.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Callable, Sequence

import numpy as np

from mirage.core import ActionType
from mirage.policies.base import ScientificPolicy
from mirage.rl.belief import BeliefTracker
from mirage.rl.gym_env import BinderCampaignEnv
from mirage.rl.observation import ACTION_INDEX, ACTION_ORDER
from mirage.rl.reward import RewardConfig

PolicyFactory = Callable[[BeliefTracker | None], ScientificPolicy]


def rollout_policy(policy: ScientificPolicy, seeds: Sequence[int], *, randomize: bool, stage: int = 4,
                   particles: int = 256, reward: RewardConfig | None = None, belief_source_factory=None) -> list[dict]:
    """One episode per seed, identical worlds for every policy. Returns episode summaries."""
    episodes = []
    for seed in seeds:
        env = BinderCampaignEnv([seed], stage=stage, randomize=randomize, sequential=True, reward=reward, particles=particles)
        env.reset()
        policy.reset(seed)
        if belief_source_factory is not None:  # policies that need the controller-held particle belief
            belief_source_factory(env)
        done, info = False, {}
        while not done:
            action = policy.choose_action(env.public_state, env.public_summary, env.public_available)
            _, _, done, _, info = env.step(ACTION_INDEX[action.action_type])
        episodes.append(info["episode_summary"])
    return episodes


def summarise(episodes: list[dict]) -> dict:
    """Aggregate training-utility statistics (never a scientific claim)."""
    if not episodes:
        return {}
    n = len(episodes)
    decisions = Counter(e["decision"] for e in episodes)
    actions = np.sum([e["action_counts"] for e in episodes], axis=0)
    by_mode: dict[str, list[dict]] = defaultdict(list)
    for e in episodes:
        by_mode[e["world_mode"]].append(e)
    def core(es: list[dict]) -> dict:
        m = len(es)
        return {
            "episodes": m,
            "return_mean": float(np.mean([e["return"] for e in es])),
            "terminal_utility_mean": float(np.mean([e["terminal_utility"] for e in es])),
            "terminal_utility_pos_rate": float(np.mean([e["terminal_utility"] > 0 for e in es])),
            "wrong_decision_rate": float(np.mean([e["terminal_utility"] < 0 for e in es])),
            "steps_mean": float(np.mean([e["steps"] for e in es])),
            "budget_spent_mean": float(np.mean([e["budget_spent"] for e in es])),
            "sample_spent_mean": float(np.mean([e["sample_spent"] for e in es])),
            "simulated_time_mean": float(np.mean([e["simulated_time"] for e in es])),
            "redesigns_mean": float(np.mean([e["redesigns"] for e in es])),
            "spr_health_lost_mean": float(np.mean([1.0 - e["spr_health_final"] for e in es])),
            "illegal_rate": float(np.mean([e["illegal"] for e in es])),
        }
    total = float(actions.sum()) or 1.0
    return {
        **core(episodes),
        "terminal_rate": float(np.mean([e["decision"] is not None for e in episodes])),
        "decision_distribution": {k: v / n for k, v in sorted(decisions.items(), key=lambda kv: str(kv[0]))},
        "action_distribution": {ACTION_ORDER[i].value: float(actions[i] / total) for i in range(len(ACTION_ORDER))},
        "by_world_mode": {mode: core(es) for mode, es in sorted(by_mode.items())},
    }
