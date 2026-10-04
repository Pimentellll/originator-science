"""PPOPolicy: a trained MaskablePPO checkpoint behind the common ScientificPolicy contract.

Inputs are exactly (AgentState, BeliefSummary, available actions); it never receives the
environment, particles or truth, and keeps no per-episode state, so replay is deterministic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from mirage.belief.summary import BeliefSummary
from mirage.core import AgentState, ScientificAction
from mirage.policies.base import PolicyError, ScientificPolicy
from mirage.rl.observation import ACTION_ORDER, action_mask, build_observation


class PPOPolicy(ScientificPolicy):
    name = "ppo"

    def __init__(self, checkpoint: str | Path | None = None, *, model=None, deterministic: bool = True, seed: int | None = None) -> None:
        if model is None:
            from sb3_contrib import MaskablePPO  # optional dependency: pip install -e .[rl]

            model = MaskablePPO.load(str(checkpoint), device="cpu")
        self.checkpoint = None if checkpoint is None else str(checkpoint)
        self.model = model
        self.deterministic = deterministic
        if seed is not None:
            self.model.set_random_seed(seed)

    def reset(self, seed: int | None = None) -> None:
        if seed is not None and not self.deterministic:
            self.model.set_random_seed(seed)

    def choose_action(self, state: AgentState, belief: BeliefSummary, available_actions: Sequence[ScientificAction]) -> ScientificAction:
        self._require_decidable(state, available_actions)
        obs = build_observation(state, belief, available_actions)
        mask = action_mask(state, available_actions)
        index, _ = self.model.predict(obs, action_masks=mask, deterministic=self.deterministic)
        kind = ACTION_ORDER[int(index)]
        for action in available_actions:
            if action.action_type == kind and action.candidate_id in (state.active_candidate.candidate_id, None):
                return action
        raise PolicyError(f"checkpoint chose {kind.value}, which is not available")
