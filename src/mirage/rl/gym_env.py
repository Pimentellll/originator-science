"""Gymnasium wrapper around the REAL Binder BioPOMDP (F0).

Observation: ``observation.build_observation`` (public features only).
Action: ``Discrete(14)``, the canonical ActionType order; legal actions via ``action_masks()``
(from ``environment.available_actions()``), for sb3-contrib ``MaskablePPO``.
Reward: ``reward.step_reward``; training signal only.

Privileged data (world mode, hidden-truth terminal utility) lives on the training side of
this wrapper. It reaches ``info`` for logging and never reaches the observation.
"""

from __future__ import annotations

from typing import Any, Sequence

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from mirage.core import ActionType
from mirage.rl.belief import DEFAULT_PARTICLES, BeliefTracker
from mirage.rl.binder_env import RandomizedBinderPOMDP
from mirage.rl.observation import ACTION_INDEX, MAX_STEPS, N_ACTIONS, NON_TERMINAL, OBS_DIM, action_mask, build_observation, n_steps, to_action
from mirage.rl.randomization import FULL_STAGE, TRAIN_SEEDS, WorldConfig, sample_world_config
from mirage.rl.reward import RewardConfig, step_reward


class BinderCampaignEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(
        self,
        seeds: Sequence[int] = TRAIN_SEEDS,
        *,
        stage: int = FULL_STAGE,
        randomize: bool = True,
        sequential: bool = False,
        reward: RewardConfig | None = None,
        particles: int = DEFAULT_PARTICLES,
    ) -> None:
        super().__init__()
        self.observation_space = spaces.Box(-5.0, 5.0, shape=(OBS_DIM,), dtype=np.float32)
        self.action_space = spaces.Discrete(N_ACTIONS)
        self._seeds, self.stage, self.randomize, self.sequential = seeds, stage, randomize, sequential
        self.reward_cfg, self.particles = reward or RewardConfig(), particles
        self._cursor = 0
        self.env: RandomizedBinderPOMDP | None = None
        self.config: WorldConfig | None = None

    def set_stage(self, stage: int) -> None:
        self.stage = stage

    # -- gymnasium API -----------------------------------------------------------------
    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None):
        super().reset(seed=seed)
        if options and "episode_seed" in options:
            episode_seed = int(options["episode_seed"])
        elif self.sequential:
            episode_seed = int(self._seeds[self._cursor % len(self._seeds)])
            self._cursor += 1
        else:
            episode_seed = int(self._seeds[int(self.np_random.integers(len(self._seeds)))])
        self.episode_seed = episode_seed
        self.config = sample_world_config(episode_seed, self.stage, randomize=self.randomize)
        self.env = RandomizedBinderPOMDP(self.config)
        self._state = self.env.reset(episode_seed)
        self.tracker = BeliefTracker(episode_seed, self.particles)
        self._summary = self.tracker.summary()
        self._available = self.env.available_actions()
        self._action_counts = np.zeros(N_ACTIONS, dtype=np.int64)
        self._return = 0.0
        self._budget0, self._sample0 = self._state.resources.budget_remaining, self._state.resources.sample_remaining
        return self._obs(), {}

    def step(self, action: int):
        assert self.env is not None, "call reset() first"
        state, summary = self._state, self._summary
        scientific = to_action(action, state)
        if scientific not in self._available or not action_mask(state, self._available)[int(action)]:
            reward = self.reward_cfg.illegal_penalty
            self._return += reward
            return self._obs(), reward, True, False, self._episode_info(None, illegal=True, terms={"illegal": reward})

        self._action_counts[int(action)] += 1
        before = state.resources
        result = self.env.step(scientific)
        self.tracker.update(scientific, result)
        self._state, self._summary = result.state, self.tracker.summary()
        self._available = self.env.available_actions()
        after = self._state.resources
        terminal = result.terminal
        reward, terms = step_reward(
            self.reward_cfg,
            entropy_before=summary.posterior_entropy,
            entropy_after=self._summary.posterior_entropy,
            budget_spent=before.budget_remaining - after.budget_remaining,
            sample_spent=before.sample_remaining - after.sample_remaining,
            time_elapsed=after.simulated_time - before.simulated_time,
            spr_health_lost=before.spr_instrument_health - after.spr_instrument_health,
            is_redesign=scientific.action_type in (ActionType.REDESIGN_STABILITY, ActionType.REDESIGN_SOLUBILITY, ActionType.REDESIGN_INTERFACE),
            redesign_count=len(self._state.candidates) - 1,
            terminal_utility=self.env.terminal_utility(self.reward_cfg.abstain_value) if terminal else None,
        )
        self._return += reward
        info = self._episode_info(scientific.action_type, terms=terms) if terminal else {"reward_terms": terms}
        return self._obs(), float(reward), terminal, False, info

    # Public views, for running any ScientificPolicy against this environment.
    @property
    def public_state(self):
        return self._state

    @property
    def public_summary(self):
        return self._summary

    @property
    def public_available(self):
        return self._available

    def action_masks(self) -> np.ndarray:
        return action_mask(self._state, self._available)

    # -- helpers -----------------------------------------------------------------------
    def _obs(self) -> np.ndarray:
        return build_observation(self._state, self._summary, self._available)

    def _episode_info(self, decision: ActionType | None, *, illegal: bool = False, terms: dict[str, float] | None = None) -> dict[str, Any]:
        res = self._state.resources
        return {
            "reward_terms": terms or {},
            "episode_summary": {
                "episode_seed": self.episode_seed,
                "world_mode": self.config.world_mode.value,  # privileged; logging only, never an observation
                "decision": None if decision is None else decision.value,
                "illegal": illegal,
                "terminal_utility": float(self.env.terminal_utility(self.reward_cfg.abstain_value)) if self.env.is_terminal() else 0.0,
                "return": float(self._return),
                "steps": n_steps(self._state),
                "redesigns": len(self._state.candidates) - 1,
                "budget_spent": self._budget0 - res.budget_remaining,
                "sample_spent": self._sample0 - res.sample_remaining,
                "simulated_time": res.simulated_time,
                "spr_health_final": res.spr_instrument_health,
                "degenerate_updates": self.tracker.degenerate_updates,
                "action_counts": self._action_counts.tolist(),
            },
        }
