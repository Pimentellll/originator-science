"""Executable public facade for the seeded Binder BioPOMDP."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from mirage.core import ActionType, AgentState, Candidate, ResourceState, ScientificAction, ScientificEnvironment, ScientificObservation, StepResult
from mirage.evaluation.campaign.truth import FailureLabels
from mirage.environments.binder.predictive import BinderHypothesis, BinderPredictiveModel
from mirage.environments.binder.scenarios import BinderScenarioVersion, BinderWorldMode, sample_world, showcase_for_mode, showcase_scenario


@dataclass(frozen=True)
class _ActionCost:
    budget: float
    sample: float
    time: float


_MEASUREMENTS = frozenset({ActionType.MEASURE_STABILITY, ActionType.MEASURE_SEC, ActionType.MEASURE_SPR, ActionType.MEASURE_EPITOPE, ActionType.MEASURE_DEVELOPABILITY, ActionType.VALIDATE_ASSAY, ActionType.ORTHOGONAL_FUNCTION})
_TERMINAL = frozenset({ActionType.SELECT, ActionType.REJECT, ActionType.MODEL_INVALID, ActionType.ABSTAIN})
_COSTS = {
    ActionType.MEASURE_STABILITY: _ActionCost(1.0, 0.5, 0.5),
    ActionType.MEASURE_SEC: _ActionCost(1.0, 0.5, 0.5),
    ActionType.MEASURE_SPR: _ActionCost(2.0, 1.0, 1.0),
    ActionType.MEASURE_EPITOPE: _ActionCost(1.0, 0.4, 0.5),
    ActionType.MEASURE_DEVELOPABILITY: _ActionCost(1.0, 0.4, 0.5),
    ActionType.VALIDATE_ASSAY: _ActionCost(0.75, 0.1, 0.25),
    ActionType.ORTHOGONAL_FUNCTION: _ActionCost(1.5, 0.25, 0.75),
    ActionType.REDESIGN_STABILITY: _ActionCost(2.0, 1.0, 1.0),
    ActionType.REDESIGN_SOLUBILITY: _ActionCost(2.0, 1.0, 1.0),
    ActionType.REDESIGN_INTERFACE: _ActionCost(2.0, 1.0, 1.0),
}


class BinderBioPOMDP(ScientificEnvironment):
    """A deterministic-by-seed environment with private causal state."""

    def __init__(self, world_mode: BinderWorldMode = BinderWorldMode.MIXED, *, scenario_version: BinderScenarioVersion = BinderScenarioVersion.BASELINE_V1) -> None:
        self._world_mode = BinderWorldMode(world_mode)
        self._scenario_version = BinderScenarioVersion(scenario_version)
        self._predictive = BinderPredictiveModel()
        self._rng = np.random.default_rng()
        self._hidden_by_candidate: dict[str, BinderHypothesis] = {}
        self._candidates: list[Candidate] = []
        self._active_id = ""
        self._resources = ResourceState(budget_remaining=0, sample_remaining=0, simulated_time=0, spr_instrument_health=1)
        self._observations: list[ScientificObservation] = []
        self._terminal = False
        self._decision: ActionType | None = None
        self.reset()

    @classmethod
    def from_showcase(cls, name: str, *, scenario_version: BinderScenarioVersion = BinderScenarioVersion.BASELINE_V1) -> "BinderBioPOMDP":
        """Construct an environment for one canonical showcase scenario."""
        return cls(showcase_scenario(name).world_mode, scenario_version=scenario_version)

    def reset(self, seed: int | None = None) -> AgentState:
        self._rng = np.random.default_rng(seed)
        root = Candidate(candidate_id="binder-000", generation=0)
        self._hidden_by_candidate = {root.candidate_id: sample_world(self._world_mode, self._rng, self._scenario_version)}
        self._candidates, self._active_id = [root], root.candidate_id
        self._resources = ResourceState(budget_remaining=12.0, sample_remaining=8.0, simulated_time=0.0, spr_instrument_health=1.0)
        self._observations, self._terminal, self._decision = [], False, None
        return self.agent_state()

    def available_actions(self) -> tuple[ScientificAction, ...]:
        if self._terminal:
            return ()
        return tuple(ScientificAction(action_type=kind, candidate_id=self._active_id) for kind in ActionType if kind in _TERMINAL or self._can_pay(_COSTS[kind]))

    def step(self, action: ScientificAction) -> StepResult:
        if self._terminal:
            raise ValueError("episode is terminal; call reset() before step()")
        if action not in self.available_actions():
            raise ValueError("action is unavailable for the current public state")
        if action.action_type in _TERMINAL:
            self._terminal, self._decision = True, action.action_type
            return StepResult(action=action, state=self.agent_state(), terminal=True)
        self._charge(_COSTS[action.action_type])
        if action.action_type in _MEASUREMENTS:
            observation = self._measure(action)
            self._observations.append(observation)
            return StepResult(action=action, observation=observation, state=self.agent_state(), terminal=False)
        self._redesign(action)
        return StepResult(action=action, state=self.agent_state(), terminal=False)

    def agent_state(self) -> AgentState:
        active = next(candidate for candidate in self._candidates if candidate.candidate_id == self._active_id)
        return AgentState(active_candidate=active, candidates=tuple(self._candidates), resources=self._resources, observations=tuple(self._observations), terminal=self._terminal)

    def evaluator_truth(self, candidate_id: str) -> "BinderEvaluatorTruth":
        """Return evaluator-only truth; policies, DTOs, and replay never receive it."""
        hidden = self._hidden_by_candidate[candidate_id]
        scenario = showcase_for_mode(self._world_mode)
        labels = FailureLabels(
            folding_failure=hidden.stability < 0.5,
            aggregation_failure=hidden.monomer_fraction < 0.8,
            affinity_failure=hidden.log_kd > -7.0,
            kinetic_failure=hidden.log_koff > -2.0,
            epitope_failure=not hidden.functional_epitope,
            developability_failure=hidden.developability_liability > 0.5,
            assay_invalid=not hidden.assay_valid,
            model_invalid=not hidden.model_valid,
        )
        if self._scenario_version == BinderScenarioVersion.SEMANTICS_V2:
            labels = labels.model_copy(update={"primary_failure_mechanisms": scenario.signature.primary_failure_mechanisms, "secondary_consequences": scenario.signature.secondary_consequences})
        regime = "path_dependent" if self._world_mode == BinderWorldMode.COMPOUND_FAILURE else "invalid" if self._world_mode in {BinderWorldMode.ASSAY_FAILURE, BinderWorldMode.MODEL_FAILURE} else "myopic"
        return BinderEvaluatorTruth(labels, scenario.name, self._world_mode.value, regime)
    def is_terminal(self) -> bool:
        return self._terminal

    def score(self) -> float:
        """Return local training utility; privileged benchmark scoring remains external."""
        if not self._terminal or self._decision is None:
            return 0.0
        hidden = self._hidden_by_candidate[self._active_id]
        correct = ((self._decision == ActionType.MODEL_INVALID and not hidden.model_valid)
            or (self._decision == ActionType.SELECT and hidden.functional_epitope and hidden.assay_valid and hidden.model_valid and hidden.stability >= 0.60 and hidden.monomer_fraction >= 0.60 and hidden.developability_liability <= 0.40)
            or (self._decision == ActionType.REJECT and not hidden.functional_epitope)
            or self._decision == ActionType.ABSTAIN)
        return (1.0 if correct else -1.0) - 0.02 * (12.0 - self._resources.budget_remaining)

    def _can_pay(self, cost: _ActionCost) -> bool:
        return self._resources.budget_remaining >= cost.budget and self._resources.sample_remaining >= cost.sample

    def _charge(self, cost: _ActionCost) -> None:
        self._resources = ResourceState(budget_remaining=round(self._resources.budget_remaining - cost.budget, 8), sample_remaining=round(self._resources.sample_remaining - cost.sample, 8), simulated_time=round(self._resources.simulated_time + cost.time, 8), spr_instrument_health=self._resources.spr_instrument_health)

    def _measure(self, action: ScientificAction) -> ScientificObservation:
        hidden = self._hidden_by_candidate[self._active_id]
        observation = self._predictive.sample_observation(hidden, action, self._rng)
        if action.action_type != ActionType.MEASURE_SPR:
            return observation
        if not (hidden.monomer_fraction < 0.45 or self._resources.spr_instrument_health < 0.70):
            return observation
        health = max(0.0, self._resources.spr_instrument_health - 0.28)
        self._resources = self._resources.model_copy(update={"spr_instrument_health": health})
        means, _ = self._predictive.expected_measurements(hidden, action)
        sigma = 0.18 + (1.0 - health) * 0.08
        readings = {name: float(value + 0.35 + self._rng.normal(0.0, sigma)) for name, value in means.items()}
        return ScientificObservation(action_type=action.action_type, candidate_id=self._active_id, measurements=readings, quality="degraded", notes=("SPR result quality degraded by sample behaviour.", "SPR instrument health declined."))

    def _redesign(self, action: ScientificAction) -> None:
        parent = next(candidate for candidate in self._candidates if candidate.candidate_id == self._active_id)
        child = Candidate(candidate_id=f"binder-{len(self._candidates):03d}", generation=parent.generation + 1, parent_candidate_id=parent.candidate_id)
        self._hidden_by_candidate[child.candidate_id] = self._predictive.redesign(self._hidden_by_candidate[parent.candidate_id], action, self._rng)
        self._candidates.append(child)
        self._active_id = child.candidate_id


@dataclass(frozen=True)
class BinderEvaluatorTruth:
    """Private evaluator payload, absent from public contracts."""
    labels: FailureLabels
    scenario_name: str
    scenario_class: str
    regime: str
