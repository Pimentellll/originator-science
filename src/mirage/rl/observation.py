"""Public observation vector and action space for the campaign-level policy (F0).

``build_observation`` is a pure function of exactly the inputs the public policy contract
provides: ``AgentState``, ``BeliefSummary`` and the currently available actions. The gym
environment and the benchmark-time ``PPOPolicy`` both call it, so a trained checkpoint sees
identical features in both places. It reads no environment object and no hidden truth.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from mirage.belief.summary import BeliefSummary
from mirage.core import ActionType, AgentState, ScientificAction

# Canonical 14-action discrete space, in ActionType declaration order.
ACTION_ORDER: tuple[ActionType, ...] = tuple(ActionType)
ACTION_INDEX: dict[ActionType, int] = {a: i for i, a in enumerate(ACTION_ORDER)}
N_ACTIONS = len(ACTION_ORDER)
assert N_ACTIONS == 14

MEASURE_ACTIONS = (
    ActionType.MEASURE_STABILITY, ActionType.MEASURE_SEC, ActionType.MEASURE_SPR, ActionType.MEASURE_EPITOPE,
    ActionType.MEASURE_DEVELOPABILITY, ActionType.VALIDATE_ASSAY, ActionType.ORTHOGONAL_FUNCTION,
)
REDESIGN_ACTIONS = (ActionType.REDESIGN_STABILITY, ActionType.REDESIGN_SOLUBILITY, ActionType.REDESIGN_INTERFACE)
NON_TERMINAL = MEASURE_ACTIONS + REDESIGN_ACTIONS

FAILURE_FIELDS = (
    "p_folding_failure", "p_aggregation_failure", "p_affinity_failure", "p_kinetic_failure",
    "p_epitope_failure", "p_developability_failure", "p_assay_invalid", "p_model_invalid",
)
# (name, centre, scale): continuous summary factors, standardised by fixed public constants.
CONTINUOUS = (
    ("stability", 0.5, 0.5), ("monomer_fraction", 0.5, 0.5), ("log_kd", -7.5, 2.5),
    ("log_koff", -2.5, 2.5), ("functional_epitope", 0.5, 0.5), ("developability_liability", 0.5, 0.5),
)

MAX_STEPS = 40  # non-terminal action limit used for the step-fraction feature and truncation
_MAX_ENTROPY = 8.0 * math.log(2.0)
_NOMINAL_BUDGET, _NOMINAL_SAMPLE, _TIME_SCALE, _ESS_REF = 12.0, 8.0, 10.0, 512.0

FEATURE_NAMES: tuple[str, ...] = (
    *FAILURE_FIELDS,
    "posterior_entropy_norm", "ess_norm",
    *(f"mean_{name}" for name, _, _ in CONTINUOUS),
    *(f"std_{name}" for name, _, _ in CONTINUOUS),
    "budget_remaining", "sample_remaining", "simulated_time", "spr_instrument_health",
    "step_fraction", "redesign_count", "active_generation",
    *(f"measured_{a.value}" for a in MEASURE_ACTIONS),
    "degraded_observations",
    *(f"affordable_{a.value}" for a in NON_TERMINAL),
)
OBS_DIM = len(FEATURE_NAMES)


def build_observation(state: AgentState, belief: BeliefSummary, available: Sequence[ScientificAction]) -> np.ndarray:
    """Public feature vector, float32, shape (OBS_DIM,)."""
    active = state.active_candidate
    own = [o for o in state.observations if o.candidate_id == active.candidate_id]
    measured = {o.action_type for o in own}
    offered = {a.action_type for a in available}
    redesigns = len(state.candidates) - 1
    steps = n_steps(state)

    f: list[float] = [float(getattr(belief, name)) for name in FAILURE_FIELDS]
    f.append(belief.posterior_entropy / _MAX_ENTROPY)
    f.append(min(belief.effective_sample_size / _ESS_REF, 1.0))
    f.extend((belief.continuous_means.get(name, centre) - centre) / scale for name, centre, scale in CONTINUOUS)
    f.extend(math.sqrt(max(belief.continuous_variances.get(name, 0.0), 0.0)) / scale for name, _, scale in CONTINUOUS)
    r = state.resources
    f.extend((r.budget_remaining / _NOMINAL_BUDGET, r.sample_remaining / _NOMINAL_SAMPLE, r.simulated_time / _TIME_SCALE, r.spr_instrument_health))
    f.extend((steps / MAX_STEPS, redesigns / 4.0, active.generation / 4.0))
    f.extend(1.0 if a in measured else 0.0 for a in MEASURE_ACTIONS)
    f.append(min(sum(o.quality == "degraded" for o in own), 3) / 3.0)
    f.extend(1.0 if a in offered else 0.0 for a in NON_TERMINAL)
    return np.clip(np.asarray(f, dtype=np.float32), -5.0, 5.0)


def n_steps(state: AgentState) -> int:
    """Non-terminal actions taken so far (each leaves exactly one observation or one new candidate)."""
    return len(state.observations) + len(state.candidates) - 1


def action_mask(state: AgentState, available: Sequence[ScientificAction]) -> np.ndarray:
    """Boolean mask over the 14 discrete actions from ``environment.available_actions()``.

    After ``MAX_STEPS`` non-terminal actions only the decisive actions stay legal, so an
    episode can never run past the cap. A terminal state yields an ABSTAIN-only mask so the
    mask is never empty.
    """
    mask = np.zeros(N_ACTIONS, dtype=bool)
    for a in available:
        mask[ACTION_INDEX[a.action_type]] = True
    if n_steps(state) >= MAX_STEPS:
        for a in NON_TERMINAL:
            mask[ACTION_INDEX[a]] = False
    if not mask.any():
        mask[ACTION_INDEX[ActionType.ABSTAIN]] = True
    return mask


def to_action(index: int, state: AgentState) -> ScientificAction:
    return ScientificAction(action_type=ACTION_ORDER[int(index)], candidate_id=state.active_candidate.candidate_id)
