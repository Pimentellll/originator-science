"""Public-evidence long-horizon rescue policy for the frozen receptor-binder profile."""

from __future__ import annotations

from typing import Sequence

from mirage.belief.summary import BeliefSummary
from mirage.core import ActionType, AgentState, ScientificAction
from mirage.policies.base import PolicyError, ScientificPolicy, threshold_terminal_decision, usable_actions


class ReceptorRescuePlannerPolicy(ScientificPolicy):
    """Protect later kinetic evidence when public SEC identifies severe aggregation.

    The policy reacts to the public monomer-fraction observation; it has no
    access to a world mode, latent state, or environment object. A solubility
    redesign is selected only after severe aggregation is observed and only
    while resources make that intervention legal.
    It rules out the assay before committing when its belief still doubts it.
    """

    name = "receptor_rescue_planner"

    def __init__(
        self,
        severe_aggregation_threshold: float = 0.45,
        decision_threshold: float = 0.5,
        assay_doubt_threshold: float = 0.2,
    ) -> None:
        self.severe_aggregation_threshold = severe_aggregation_threshold
        self.decision_threshold = decision_threshold
        self.assay_doubt_threshold = assay_doubt_threshold

    def choose_action(self, state: AgentState, belief: BeliefSummary, available_actions: Sequence[ScientificAction]) -> ScientificAction:
        self._require_decidable(state, available_actions)
        usable = usable_actions(state, available_actions)
        current = state.active_candidate
        sec = next((o for o in reversed(state.observations) if o.candidate_id == current.candidate_id and o.action_type == ActionType.MEASURE_SEC), None)
        parent_sec = next((o for o in reversed(state.observations) if o.candidate_id == current.parent_candidate_id and o.action_type == ActionType.MEASURE_SEC), None)
        if sec is None and current.parent_candidate_id is None and ActionType.MEASURE_SEC in usable:
            return usable[ActionType.MEASURE_SEC]
        severe = (sec or parent_sec) is not None and (sec or parent_sec).measurements["monomer_fraction"] < self.severe_aggregation_threshold
        if severe and current.parent_candidate_id is None and ActionType.REDESIGN_SOLUBILITY in usable:
            return usable[ActionType.REDESIGN_SOLUBILITY]
        if ActionType.MEASURE_SPR in usable and not any(o.candidate_id == current.candidate_id and o.action_type == ActionType.MEASURE_SPR for o in state.observations):
            return usable[ActionType.MEASURE_SPR]
        if (
            belief.p_assay_invalid > self.assay_doubt_threshold
            and ActionType.VALIDATE_ASSAY in usable
            and not any(o.action_type == ActionType.VALIDATE_ASSAY for o in state.observations)
        ):
            return usable[ActionType.VALIDATE_ASSAY]
        return threshold_terminal_decision(belief, usable, self.decision_threshold)
