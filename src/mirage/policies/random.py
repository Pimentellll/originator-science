"""Seeded uniform-random baseline over legal public actions."""

from __future__ import annotations

from typing import Sequence

import numpy as np

from mirage.belief.summary import BeliefSummary
from mirage.core.contracts import AgentState, ScientificAction
from mirage.policies.base import TERMINAL_ACTIONS, PolicyError, ScientificPolicy, sorted_actions


class RandomPolicy(ScientificPolicy):
    """Uniform over ``available_actions`` (terminal decisions included by default).

    The belief is ignored. ``reset(seed)`` restarts the stream, so the same
    seed and the same sequence of available-action sets reproduce the same
    choices.
    """

    name = "random"

    def __init__(self, seed: int = 0, allow_terminal: bool = True) -> None:
        self._base_seed = seed
        self.allow_terminal = allow_terminal
        self._rng = np.random.default_rng(seed)

    def reset(self, seed: int | None = None) -> None:
        if seed is not None:
            self._base_seed = seed
        self._rng = np.random.default_rng(self._base_seed)

    def choose_action(
        self,
        state: AgentState,
        belief: BeliefSummary,
        available_actions: Sequence[ScientificAction],
    ) -> ScientificAction:
        self._require_decidable(state, available_actions)
        pool = sorted_actions(available_actions)
        if not self.allow_terminal:
            pool = [a for a in pool if a.action_type not in TERMINAL_ACTIONS] or pool
        if not pool:
            raise PolicyError("no available actions")
        return pool[int(self._rng.integers(len(pool)))]
