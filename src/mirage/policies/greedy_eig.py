"""Myopic one-step expected-information-gain baseline."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

import numpy as np

from mirage.belief.acquisition import expected_information_gain, sample_sources
from mirage.belief.particles import ParticleBelief
from mirage.belief.predictive import ParticlePredictiveModel
from mirage.belief.summary import BeliefSummary
from mirage.core.contracts import ActionType, AgentState, ScientificAction
from mirage.policies.base import (
    MEASUREMENT_ACTIONS,
    ScientificPolicy,
    check_belief_in_sync,
    sorted_actions,
    threshold_terminal_decision,
    usable_actions,
)


@dataclass(frozen=True)
class ActionScore:
    eig: float  # nats; one-step expected reduction of total marginal mechanism entropy
    cost: float  # configured relative cost (1.0 when not cost-aware)
    score: float  # eig, or eig / normalised cost
    tempering: float = 1.0  # <1 when the EIG estimator had to temper the likelihood (see acquisition)


class GreedyEIGPolicy(ScientificPolicy):
    """Pick the available assay with the largest one-step expected information gain.

    Strictly myopic: each assay is scored only by the entropy it is expected to
    remove from the CURRENT belief after its own single observation. There is no
    multi-step search, no lookahead over resulting beliefs and no model of future
    instrument health (e.g. SPR damage) beyond whatever the immediate observation
    model already implies for this observation.

    Redesign and terminal actions carry no immediate observation, so they have
    zero EIG. The policy therefore measures while ``max score >= min_eig`` and
    otherwise closes with the shared public threshold rule; it never redesigns.

    Cost-aware variant: pass ``costs`` (relative public configuration, not
    simulator truth). Score = EIG / (cost / mean cost of the candidate assays),
    which is scale-free; unlisted actions cost 1.0.

    Collaborators: ``belief_source`` returns the controller-maintained
    ParticleBelief (hypothetical particles only, never mutated here). The
    ``belief`` argument is the public summary of that same belief and is checked
    for consistency, so a stale handle fails loudly. The policy does not receive
    the environment.
    """

    name = "greedy_eig"

    def __init__(
        self,
        model: ParticlePredictiveModel,
        belief_source: Callable[[], ParticleBelief],
        *,
        seed: int = 0,
        n_samples: int = 64,
        costs: Mapping[ActionType, float] | None = None,
        min_eig: float = 0.02,
        min_posterior_ess: float = 10.0,
        decision_threshold: float = 0.5,
    ) -> None:
        if n_samples < 1:
            raise ValueError("n_samples must be >= 1")
        if costs is not None and any(c <= 0 for c in costs.values()):
            raise ValueError("costs must be positive")
        self.model = model
        self.belief_source = belief_source
        self.n_samples = n_samples
        self.costs = dict(costs) if costs is not None else None
        self.min_eig = min_eig
        self.min_posterior_ess = min_posterior_ess
        self.decision_threshold = decision_threshold
        self._base_seed = seed
        self._rng = np.random.default_rng(seed)
        self.last_scores: dict[ActionType, ActionScore] = {}
        self.last_decision_seconds: float = 0.0

    def reset(self, seed: int | None = None) -> None:
        if seed is not None:
            self._base_seed = seed
        self._rng = np.random.default_rng(self._base_seed)
        self.last_scores = {}

    def score_actions(
        self, belief: ParticleBelief, candidates: Sequence[ScientificAction]
    ) -> dict[ActionType, ActionScore]:
        """EIG (and cost-adjusted score) for each action, sharing hypothetical sources."""
        sources = sample_sources(belief, self._rng, self.n_samples)
        est = {
            a.action_type: expected_information_gain(
                belief,
                self.model,
                a,
                n_samples=self.n_samples,
                rng=self._rng,
                source_indices=sources,
                min_posterior_ess=self.min_posterior_ess,
            )
            for a in candidates
        }
        cost = {t: 1.0 if self.costs is None else self.costs.get(t, 1.0) for t in est}
        mean_cost = float(np.mean(list(cost.values())))
        return {
            t: ActionScore(
                e.eig,
                cost[t],
                e.eig if self.costs is None else e.eig / (cost[t] / mean_cost),
                e.tempering,
            )
            for t, e in est.items()
        }

    def choose_action(
        self,
        state: AgentState,
        belief: BeliefSummary,
        available_actions: Sequence[ScientificAction],
    ) -> ScientificAction:
        self._require_decidable(state, available_actions)
        started = time.perf_counter()
        particle_belief = self.belief_source()
        check_belief_in_sync(particle_belief, belief)

        usable = usable_actions(state, available_actions)
        candidates = [a for a in sorted_actions(list(usable.values())) if a.action_type in MEASUREMENT_ACTIONS]
        self.last_scores = self.score_actions(particle_belief, candidates) if candidates else {}
        self.last_decision_seconds = time.perf_counter() - started

        if self.last_scores:
            best = max(self.last_scores, key=lambda t: self.last_scores[t].score)  # first max in sorted order
            if self.last_scores[best].score >= self.min_eig:
                return usable[best]
        return threshold_terminal_decision(belief, usable, self.decision_threshold)
