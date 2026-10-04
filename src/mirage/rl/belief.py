"""Public belief tracking for the gym environment.

Mirrors the integration controller's ``BinderBeliefSession`` protocol (observe on every
observation, ``apply_redesign`` on every redesign) and its public ``receptor_binder_prior``,
so PPO and the Greedy EIG baseline reason from the same belief. Hidden truth is never read.

Known model mismatch handled here: the environment can emit a "degraded" SPR reading because
instrument health fell, while the public likelihood only allows "degraded" for aggregated
particles. If every particle then has zero likelihood the belief raises
``DegenerateBeliefError``; the tracker keeps the previous belief and counts the event.
"""

from __future__ import annotations

from mirage.belief import (
    BINDER_SCHEMA_PROVISIONAL, DegenerateBeliefError, IndependentPrior, ParticleBelief, bernoulli, uniform,
)
from mirage.belief.binder import BinderParticleModel
from mirage.belief.summary import BeliefSummary
from mirage.core import ScientificAction, StepResult
from mirage.policies.base import REDESIGN_ACTIONS

DEFAULT_PARTICLES = 256


def receptor_binder_prior() -> IndependentPrior:
    """Public semi-mechanistic prior (same values as the integration controller's)."""
    return IndependentPrior(BINDER_SCHEMA_PROVISIONAL, {
        "stability": uniform(0.05, 1.0),
        "monomer_fraction": uniform(0.05, 1.0),
        "log_kd": uniform(-10.0, -5.0),
        "log_koff": uniform(-5.0, 0.0),
        "functional_epitope": bernoulli(0.75),
        "developability_liability": uniform(0.0, 1.0),
        "assay_valid": bernoulli(0.85),
        "model_valid": bernoulli(0.85),
    })


class BeliefTracker:
    def __init__(self, seed: int, particles: int = DEFAULT_PARTICLES) -> None:
        self.model = BinderParticleModel()
        self.belief = ParticleBelief.from_prior(BINDER_SCHEMA_PROVISIONAL, receptor_binder_prior(), n=particles, seed=seed)
        self.degenerate_updates = 0

    def summary(self) -> BeliefSummary:
        return self.belief.summary()

    def update(self, action: ScientificAction, result: StepResult) -> None:
        if result.observation is not None:
            try:
                self.belief.observe(self.model, action, result.observation)
            except DegenerateBeliefError:
                self.degenerate_updates += 1
        elif action.action_type in REDESIGN_ACTIONS:
            self.belief.apply_redesign(self.model, action)
