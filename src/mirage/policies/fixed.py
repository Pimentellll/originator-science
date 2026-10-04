"""Static conventional-laboratory workflow baseline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from mirage.belief.summary import BeliefSummary
from mirage.core.contracts import ActionType, AgentState, ScientificAction
from mirage.policies.base import (
    PolicyError,
    ScientificPolicy,
    threshold_terminal_decision,
    usable_actions,
)

# QC-before-SPR order, as a conventional workflow would run it.
DEFAULT_PIPELINE: tuple[ActionType, ...] = (
    ActionType.MEASURE_STABILITY,
    ActionType.MEASURE_SEC,
    ActionType.MEASURE_SPR,
    ActionType.MEASURE_EPITOPE,
    ActionType.MEASURE_DEVELOPABILITY,
    ActionType.VALIDATE_ASSAY,
    ActionType.ORTHOGONAL_FUNCTION,
)


@dataclass(frozen=True)
class FixedPipelineConfig:
    sequence: tuple[ActionType, ...] = DEFAULT_PIPELINE
    decision_threshold: float = 0.5


class FixedPipelinePolicy(ScientificPolicy):
    """Run every assay once on the active candidate, in a fixed order, then decide.

    The measurement order never depends on results. Progress is read from the
    public observation log (stateless, replay-safe); an assay that is not
    currently available (e.g. insufficient resources) is skipped. The closing
    decision is a fixed rule on the public belief:

        p_assay_invalid >= t                    -> ABSTAIN
        p_model_invalid >= t                    -> MODEL_INVALID
        any molecular failure marginal >= t     -> REJECT
        otherwise                               -> SELECT

    It never redesigns.
    """

    name = "fixed_pipeline"

    def __init__(self, config: FixedPipelineConfig | None = None) -> None:
        self.config = config or FixedPipelineConfig()

    def choose_action(
        self,
        state: AgentState,
        belief: BeliefSummary,
        available_actions: Sequence[ScientificAction],
    ) -> ScientificAction:
        self._require_decidable(state, available_actions)
        cid = state.active_candidate.candidate_id
        usable = usable_actions(state, available_actions)

        done = {o.action_type for o in state.observations if o.candidate_id == cid}
        for action_type in self.config.sequence:
            if action_type not in done and action_type in usable:
                return usable[action_type]

        try:
            return threshold_terminal_decision(belief, usable, self.config.decision_threshold)
        except PolicyError as exc:
            raise PolicyError("pipeline exhausted and no terminal action is available") from exc
