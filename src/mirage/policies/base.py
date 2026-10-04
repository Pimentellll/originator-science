"""The common public policy contract shared by every MIRAGE baseline.

A policy receives only public inputs (AgentState, BeliefSummary and the
currently available ScientificAction values). It never receives the
environment object, particles or privileged truth.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

import numpy as np

from mirage.belief.particles import ParticleBelief
from mirage.belief.summary import BeliefSummary
from mirage.core.contracts import ActionType, AgentState, ScientificAction

TERMINAL_ACTIONS = frozenset(
    {ActionType.SELECT, ActionType.REJECT, ActionType.MODEL_INVALID, ActionType.ABSTAIN}
)
REDESIGN_ACTIONS = frozenset(
    {ActionType.REDESIGN_STABILITY, ActionType.REDESIGN_SOLUBILITY, ActionType.REDESIGN_INTERFACE}
)


MEASUREMENT_ACTIONS = frozenset(ActionType) - TERMINAL_ACTIONS - REDESIGN_ACTIONS

_MOLECULAR_FIELDS = (
    "p_folding_failure",
    "p_aggregation_failure",
    "p_affinity_failure",
    "p_kinetic_failure",
    "p_epitope_failure",
    "p_developability_failure",
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


def usable_actions(
    state: AgentState, available_actions: Sequence[ScientificAction]
) -> dict[ActionType, ScientificAction]:
    """Available actions applicable to the active candidate, one per action type."""
    cid = state.active_candidate.candidate_id
    usable = {a.action_type: a for a in available_actions if a.candidate_id in (cid, None)}
    for a in available_actions:  # prefer an action explicitly bound to the active candidate
        if a.candidate_id == cid:
            usable[a.action_type] = a
    return usable


def threshold_terminal_decision(
    belief: BeliefSummary, usable: dict[ActionType, ScientificAction], threshold: float
) -> ScientificAction:
    """Shared closing rule for the non-learning baselines (public belief only).

    Checked in the order of the correct-terminal partition: a probable molecular failure
    wins first (REJECT is right whatever the assay or model did), because p(model invalid)
    is not measured by any assay and rests at its prior unless every other cause is
    eliminated.

        any molecular failure marginal >= t     -> REJECT
        p_assay_invalid >= t                    -> ABSTAIN
        p_model_invalid >= t                    -> MODEL_INVALID
        otherwise                               -> SELECT
    """
    if any(getattr(belief, f) >= threshold for f in _MOLECULAR_FIELDS):
        wanted = ActionType.REJECT
    elif belief.p_assay_invalid >= threshold:
        wanted = ActionType.ABSTAIN
    elif belief.p_model_invalid >= threshold:
        wanted = ActionType.MODEL_INVALID
    else:
        wanted = ActionType.SELECT
    if wanted in usable:
        return usable[wanted]
    for fallback in (ActionType.ABSTAIN, *sorted(TERMINAL_ACTIONS, key=lambda a: a.value)):
        if fallback in usable:
            return usable[fallback]
    raise PolicyError("no terminal action is available")


def check_belief_in_sync(particle_belief: ParticleBelief, summary: BeliefSummary) -> None:
    """Fail loudly if a policy's belief handle is not the belief that produced ``summary``."""
    mine = particle_belief.summary()
    in_sync = (
        np.isclose(mine.posterior_entropy, summary.posterior_entropy, atol=1e-9)
        and np.isclose(mine.effective_sample_size, summary.effective_sample_size, atol=1e-6)
        and all(
            np.isclose(getattr(mine, f), getattr(summary, f), atol=1e-9)
            for f in type(summary).model_fields
            if f.startswith("p_")
        )
    )
    if not in_sync:
        raise PolicyError("belief_source is out of sync with the BeliefSummary passed to choose_action")
