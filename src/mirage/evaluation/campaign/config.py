"""Versioned evaluator configuration (METRICS.md: thresholds are evaluator configuration).

Defaults are modelling assumptions of this evaluator, not biological constants. Any change
must bump ``version`` so stored evaluations stay attributable.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from mirage.core import ActionType


class EvaluatorConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = "campaign-eval/1"

    # Belief thresholds applied to the belief the policy held when it decided.
    support_max_marginal: float = Field(default=0.2, ge=0, le=1)  # "this factor is unlikely"
    support_min_marginal: float = Field(default=0.8, ge=0, le=1)  # "this factor is likely"
    recognition_threshold: float = Field(default=0.5, ge=0, le=1)  # detection for diagnostics

    # control_signal at or above this means the assay-integrity control passed.
    control_pass_threshold: float = 0.5
    # orthogonal_function_signal at or above this means function is present orthogonally.
    orthogonal_pass_threshold: float = 0.5
    # Substrings of a public ``quality`` label that mark an unreliable readout.
    degraded_quality_markers: tuple[str, ...] = ("degraded", "poor", "unreliable", "low", "bad")

    # Assays that must have been run on the candidate before a justified SELECT.
    select_required_actions: tuple[ActionType, ...] = (
        ActionType.MEASURE_STABILITY,
        ActionType.MEASURE_SEC,
        ActionType.MEASURE_SPR,
        ActionType.MEASURE_EPITOPE,
        ActionType.MEASURE_DEVELOPABILITY,
    )
    select_requires_assay_validation: bool = True
    # Cheap readouts that do not establish binding function on their own.
    proxy_actions: tuple[ActionType, ...] = (
        ActionType.MEASURE_STABILITY,
        ActionType.MEASURE_DEVELOPABILITY,
        ActionType.MEASURE_SEC,
    )
    functional_actions: tuple[ActionType, ...] = (
        ActionType.MEASURE_SPR,
        ActionType.MEASURE_EPITOPE,
        ActionType.ORTHOGONAL_FUNCTION,
    )
    # A budget/sample at or below these floors counts as exhausted (abstention is then fair).
    exhaustion_budget_floor: float = 0.0
    exhaustion_sample_floor: float = 0.0
    # Belief equality tolerance for the "terminal step must not change belief" check.
    belief_tolerance: float = 1e-9
    # Repeating the same assay on the same candidate more often than this is flagged as
    # information-gain farming (a typical shaped-reward exploit), not as a score penalty.
    max_repeat_measurements: int = Field(default=2, ge=0)
    # Abstaining without effort is not a justified conclusion: this many reliable
    # measurements (any candidate) are required unless the campaign is exhausted.
    abstain_min_measurements: int = Field(default=2, ge=0)
