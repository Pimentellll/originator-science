"""Hand-built public traces and labels for testing the evaluator and the adversarial suite.

These are scripted specification fixtures, NOT simulator output and NOT benchmark results.
They exist so evaluator semantics can be pinned before the Binder environment lands.
"""

from __future__ import annotations

from typing import Any

from mirage.core import (
    ActionType,
    AgentState,
    Candidate,
    ResourceState,
    ScientificAction,
    ScientificObservation,
)
from mirage.evaluation.campaign.truth import FailureLabels
from mirage.provenance import EpisodeRecord, PolicyMetadata, ScientificEvent
from mirage.provenance.compat import ACTION_MEASUREMENTS

# (budget, sample, time) charged per action in synthetic traces.
SYNTHETIC_COSTS: dict[ActionType, tuple[float, float, float]] = {
    ActionType.MEASURE_STABILITY: (2.0, 0.5, 1.0),
    ActionType.MEASURE_SEC: (3.0, 1.0, 2.0),
    ActionType.MEASURE_SPR: (8.0, 1.0, 3.0),
    ActionType.MEASURE_EPITOPE: (5.0, 1.0, 2.0),
    ActionType.MEASURE_DEVELOPABILITY: (3.0, 0.5, 1.0),
    ActionType.VALIDATE_ASSAY: (2.0, 0.0, 1.0),
    ActionType.ORTHOGONAL_FUNCTION: (6.0, 1.0, 3.0),
    ActionType.REDESIGN_STABILITY: (10.0, 2.0, 5.0),
    ActionType.REDESIGN_SOLUBILITY: (10.0, 2.0, 5.0),
    ActionType.REDESIGN_INTERFACE: (10.0, 2.0, 5.0),
}

_NEUTRAL = {
    "stability_proxy": 0.5,
    "monomer_fraction": 0.5,
    "log_kd": -7.0,
    "log_koff": -3.0,
    "epitope_signal": 0.5,
    "liability_proxy": 0.5,
    "control_signal": 0.9,
    "orthogonal_function_signal": 0.5,
}


def make_belief(**overrides: Any) -> dict[str, Any]:
    """A valid BeliefSummary snapshot; unspecified failure marginals are 0.5."""
    belief: dict[str, Any] = {
        "p_folding_failure": 0.5,
        "p_aggregation_failure": 0.5,
        "p_affinity_failure": 0.5,
        "p_kinetic_failure": 0.5,
        "p_epitope_failure": 0.5,
        "p_developability_failure": 0.5,
        "p_assay_invalid": 0.5,
        "p_model_invalid": 0.5,
        "posterior_entropy": 1.0,
        "continuous_means": {"log_kd": -7.0},
        "continuous_variances": {"log_kd": 1.0},
        "effective_sample_size": 256.0,
    }
    belief.update(overrides)
    return belief


def confident(**overrides: Any) -> dict[str, Any]:
    """Belief that every failure is unlikely, except as overridden."""
    base = {
        k: 0.05
        for k in (
            "p_folding_failure",
            "p_aggregation_failure",
            "p_affinity_failure",
            "p_kinetic_failure",
            "p_epitope_failure",
            "p_developability_failure",
            "p_assay_invalid",
            "p_model_invalid",
        )
    }
    base.update(overrides)
    return make_belief(**base)


class TraceBuilder:
    """Builds a self-consistent public episode, step by step."""

    def __init__(
        self,
        *,
        episode_id: str = "ep-0",
        seed: int = 0,
        policy: str = "synthetic",
        budget: float = 100.0,
        sample: float = 20.0,
        candidate: str = "cand-0",
    ) -> None:
        self.episode_id = episode_id
        self.seed = seed
        self.policy = policy
        root = Candidate(candidate_id=candidate, generation=0)
        self.resources = ResourceState(
            budget_remaining=budget, sample_remaining=sample, simulated_time=0.0, spr_instrument_health=1.0
        )
        self.initial = AgentState(
            active_candidate=root, candidates=(root,), resources=self.resources, observations=()
        )
        self.active = candidate
        self.events: list[ScientificEvent] = []
        self.terminal: ScientificAction | None = None
        self._children = 0

    def _charge(self, action: ActionType, spr_damage: float = 0.0) -> ResourceState:
        b, s, t = SYNTHETIC_COSTS.get(action, (0.0, 0.0, 0.0))
        r = self.resources
        return ResourceState(
            budget_remaining=max(0.0, r.budget_remaining - b),
            sample_remaining=max(0.0, r.sample_remaining - s),
            simulated_time=r.simulated_time + t,
            spr_instrument_health=max(0.0, r.spr_instrument_health - spr_damage),
        )

    def _add(self, **kwargs: Any) -> ScientificEvent:
        event = ScientificEvent(
            episode_id=self.episode_id,
            step=len(self.events),
            policy_name=self.policy,
            resources_before=self.resources,
            **kwargs,
        )
        self.events.append(event)
        self.resources = event.resources_after
        return event

    def measure(
        self,
        action: ActionType,
        measurements: dict[str, float] | None = None,
        *,
        quality: str = "ok",
        candidate: str | None = None,
        belief_before: dict[str, Any] | None = None,
        belief_after: dict[str, Any] | None = None,
        spr_damage: float = 0.0,
        rationale: str | None = None,
    ) -> ScientificEvent:
        cand = candidate or self.active
        values = {n: _NEUTRAL[n] for n in ACTION_MEASUREMENTS[action]}
        values.update(measurements or {})
        return self._add(
            candidate_id=cand,
            action=ScientificAction(action_type=action, candidate_id=cand),
            observation=ScientificObservation(
                action_type=action, candidate_id=cand, measurements=values, quality=quality
            ),
            belief_before=belief_before,
            belief_after=belief_after,
            resources_after=self._charge(action, spr_damage),
            rationale=rationale,
        )

    def redesign(
        self, action: ActionType, *, belief_before: dict | None = None, belief_after: dict | None = None
    ) -> ScientificEvent:
        self._children += 1
        parent = self.active
        child = f"{parent}-r{self._children}"
        event = self._add(
            candidate_id=parent,
            action=ScientificAction(action_type=action, candidate_id=parent),
            child_candidate_id=child,
            belief_before=belief_before,
            belief_after=belief_after,
            resources_after=self._charge(action),
        )
        self.active = child
        return event

    def decide(
        self,
        action: ActionType,
        belief: dict[str, Any] | None = None,
        *,
        belief_after: dict[str, Any] | None = None,
        candidate: str | None = None,
        rationale: str | None = None,
    ) -> ScientificEvent:
        cand = candidate or self.active
        event = self._add(
            candidate_id=cand,
            action=ScientificAction(action_type=action, candidate_id=cand),
            belief_before=belief,
            belief_after=belief if belief_after is None else belief_after,
            resources_after=self.resources,
            rationale=rationale,
        )
        self.terminal = event.action
        return event

    def build(self) -> EpisodeRecord:
        return EpisodeRecord(
            contract_version="mirage.core/1",
            environment_id="synthetic-fixture",
            code_version="test",
            episode_id=self.episode_id,
            seed=self.seed,
            initial_state=self.initial,
            events=tuple(self.events),
            terminal_decision=self.terminal,
            policy=PolicyMetadata(name=self.policy),
        )


class SyntheticOracle:
    """Fixed per-candidate labels; the default applies to candidates not listed."""

    def __init__(
        self,
        default: FailureLabels,
        by_candidate: dict[str, FailureLabels] | None = None,
        scenario: str = "SYNTHETIC",
        regime: str = "unspecified",
    ) -> None:
        self._default = default
        self._by = by_candidate or {}
        self._scenario = scenario
        self._regime = regime

    def failure_labels(self, candidate_id: str) -> FailureLabels:
        return self._by.get(candidate_id, self._default)

    def scenario_class(self) -> str:
        return self._scenario

    def regime(self) -> str:
        return self._regime
