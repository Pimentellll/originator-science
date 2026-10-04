"""Action taxonomy and observation accessors shared by provenance, evaluation and the API.

Measurement names follow docs/scientific-spec/ACTION_OBSERVATION_CONTRACT.md; the structured
observation shape is frozen in core (A0-FREEZE 9fe2f8e).
"""

from __future__ import annotations

from typing import Any

from mirage.core import ActionType

# Names of public assay outputs per action (ACTION_OBSERVATION_CONTRACT).
ACTION_MEASUREMENTS: dict[ActionType, tuple[str, ...]] = {
    ActionType.MEASURE_STABILITY: ("stability_proxy",),
    ActionType.MEASURE_SEC: ("monomer_fraction",),
    ActionType.MEASURE_SPR: ("log_kd", "log_koff"),
    ActionType.MEASURE_EPITOPE: ("epitope_signal",),
    ActionType.MEASURE_DEVELOPABILITY: ("liability_proxy",),
    ActionType.VALIDATE_ASSAY: ("control_signal",),
    ActionType.ORTHOGONAL_FUNCTION: ("orthogonal_function_signal",),
}

MEASUREMENT_ACTIONS = frozenset(ACTION_MEASUREMENTS)
REDESIGN_ACTIONS = frozenset(
    {
        ActionType.REDESIGN_STABILITY,
        ActionType.REDESIGN_SOLUBILITY,
        ActionType.REDESIGN_INTERFACE,
    }
)
TERMINAL_ACTIONS = frozenset(
    {
        ActionType.SELECT,
        ActionType.REJECT,
        ActionType.MODEL_INVALID,
        ActionType.ABSTAIN,
    }
)


def measurements_of(observation: Any) -> dict[str, float]:
    """Named numeric measurements of a public observation (empty if none)."""
    if observation is None:
        return {}
    return {str(k): float(v) for k, v in observation.measurements.items()}


def quality_of(observation: Any) -> str:
    """Public quality label, lower-cased; empty when no observation."""
    return "" if observation is None else observation.quality.strip().lower()
