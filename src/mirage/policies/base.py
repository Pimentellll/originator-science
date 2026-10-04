"""The common public policy contract shared by every MIRAGE baseline.

A policy receives only public inputs (AgentState, BeliefSummary and the
currently available ScientificAction values). It never receives the
environment object, particles or privileged truth.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from mirage.belief.summary import BeliefSummary
from mirage.core.contracts import ActionType, AgentState, ScientificAction

TERMINAL_ACTIONS = frozenset(
    {ActionType.SELECT, ActionType.REJECT, ActionType.MODEL_INVALID, ActionType.ABSTAIN}
)
REDESIGN_ACTIONS = frozenset(
    {ActionType.REDESIGN_STABILITY, ActionType.REDESIGN_SOLUBILITY, ActionType.REDESIGN_INTERFACE}
)


class PolicyError(RuntimeError):
    """The policy cannot produce a legal action from its inputs."""


def sorted_actions(actions: Sequence[ScientificAction]) -> list[ScientificAction]:
    """Deterministic order independent of how the environment enumerates actions."""
    return sorted(actions, key=lambda a: (a.action_type.value, a.candidate_id or ""))


class ScientificPolicy(ABC):
    """choose_action(state, belief, available_actions) -> ScientificAction."""

    name: str = "policy"

    def reset(self, seed: int | None = None) -> None:
        """Prepare for a new episode; stateless policies may ignore this."""

    @abstractmethod
    def choose_action(
        self,
        state: AgentState,
        belief: BeliefSummary,
        available_actions: Sequence[ScientificAction],
    ) -> ScientificAction:
        """Return one element of ``available_actions``."""

    @staticmethod
    def _require_decidable(state: AgentState, available_actions: Sequence[ScientificAction]) -> None:
        if state.terminal:
            raise PolicyError("episode is terminal; no action to choose")
        if not available_actions:
            raise PolicyError("no available actions")
