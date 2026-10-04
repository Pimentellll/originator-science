"""Public predictive model for hypothetical Binder BioPOMDP particles.

This module never stores an episode's actual simulator truth. The environment
may use the same equations privately, while inference supplies hypothetical
BinderHypothesis values to evaluate likelihoods or redesign transitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, log, pi

import numpy as np

from mirage.core import ActionType, ScientificAction, ScientificObservation


@dataclass(frozen=True)
class BinderHypothesis:
    """A caller-owned hypothetical factorised particle, not episode truth."""

    stability: float
    monomer_fraction: float
    log_kd: float
    log_koff: float
    functional_epitope: bool
    developability_liability: float
    assay_valid: bool
    model_valid: bool

    def __post_init__(self) -> None:
        for name in ("stability", "monomer_fraction", "developability_liability"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")


_MEASUREMENT_ACTIONS = frozenset({
    ActionType.MEASURE_STABILITY, ActionType.MEASURE_SEC, ActionType.MEASURE_SPR,
    ActionType.MEASURE_EPITOPE, ActionType.MEASURE_DEVELOPABILITY,
    ActionType.VALIDATE_ASSAY, ActionType.ORTHOGONAL_FUNCTION,
})
_REDESIGN_ACTIONS = frozenset({
    ActionType.REDESIGN_STABILITY, ActionType.REDESIGN_SOLUBILITY,
    ActionType.REDESIGN_INTERFACE,
})


class BinderPredictiveModel:
    """Auditable likelihoods for public observations of hypothetical particles."""

    def expected_measurements(
        self, hypothesis: BinderHypothesis, action: ScientificAction
    ) -> tuple[dict[str, float], str]:
        """Return public assay means and quality for a hypothetical particle."""
        h, kind = hypothesis, action.action_type
        if kind == ActionType.MEASURE_STABILITY:
            return {"stability_proxy": h.stability}, "nominal"
        if kind == ActionType.MEASURE_SEC:
            return {"monomer_fraction": h.monomer_fraction}, "nominal"
        if kind == ActionType.MEASURE_SPR:
            quality = "degraded" if h.monomer_fraction < 0.45 else "nominal"
            bias = 0.35 if quality == "degraded" else 0.0
            return {"log_kd": h.log_kd + bias, "log_koff": h.log_koff + bias}, quality
        if kind == ActionType.MEASURE_EPITOPE:
            return {"epitope_signal": 0.82 if h.functional_epitope else 0.24}, "nominal"
        if kind == ActionType.MEASURE_DEVELOPABILITY:
            return {"liability_proxy": h.developability_liability}, "nominal"
        if kind == ActionType.VALIDATE_ASSAY:
            return {"control_signal": 0.86 if h.assay_valid else 0.23}, "nominal"
        if kind == ActionType.ORTHOGONAL_FUNCTION:
            works = h.functional_epitope and h.assay_valid
            return {"orthogonal_function_signal": 0.80 if works else 0.28}, "nominal"
        raise ValueError(f"{kind.value} does not produce a measurement")

    def sample_observation(
        self, hypothesis: BinderHypothesis, action: ScientificAction, rng: np.random.Generator
    ) -> ScientificObservation:
        """Sample a structured public observation with seeded Gaussian noise."""
        means, quality = self.expected_measurements(hypothesis, action)
        sigma = 0.18 if quality == "degraded" else 0.08
        measurements = {key: float(value + rng.normal(0.0, sigma)) for key, value in means.items()}
        notes = ("SPR result quality degraded by sample behaviour.",) if quality == "degraded" else ()
        return ScientificObservation(action_type=action.action_type, candidate_id=action.candidate_id or "unknown", measurements=measurements, quality=quality, notes=notes)

    def log_likelihood(
        self, observation: ScientificObservation, hypothesis: BinderHypothesis, action: ScientificAction
    ) -> float:
        """Compute log p(observation | caller-supplied hypothesis, action)."""
        means, quality = self.expected_measurements(hypothesis, action)
        if observation.action_type != action.action_type or observation.quality != quality:
            return float("-inf")
        if set(observation.measurements) != set(means):
            return float("-inf")
        sigma = 0.18 if quality == "degraded" else 0.08
        return sum(-0.5 * ((value - means[key]) / sigma) ** 2 - log(sigma * (2 * pi) ** 0.5) for key, value in observation.measurements.items())

    def redesign(self, hypothesis: BinderHypothesis, action: ScientificAction, rng: np.random.Generator) -> BinderHypothesis:
        """Propagate a hypothetical particle through a seeded synthetic redesign."""
        if action.action_type not in _REDESIGN_ACTIONS:
            raise ValueError(f"{action.action_type.value} is not a redesign action")
        h = hypothesis
        stability, monomer, kd, koff = h.stability, h.monomer_fraction, h.log_kd, h.log_koff
        if action.action_type == ActionType.REDESIGN_STABILITY:
            stability = min(1.0, stability + rng.normal(0.24, 0.07)); monomer = min(1.0, max(0.0, monomer + rng.normal(0.06, 0.04)))
        elif action.action_type == ActionType.REDESIGN_SOLUBILITY:
            monomer = min(1.0, monomer + rng.normal(0.25, 0.07)); stability = min(1.0, max(0.0, stability + rng.normal(-0.02, 0.04)))
        else:
            kd += rng.normal(-0.45, 0.15); koff += rng.normal(-0.35, 0.15); stability = min(1.0, max(0.0, stability + rng.normal(-0.03, 0.04)))
        return BinderHypothesis(stability=max(0.0, stability), monomer_fraction=max(0.0, monomer), log_kd=kd, log_koff=koff, functional_epitope=h.functional_epitope, developability_liability=h.developability_liability, assay_valid=h.assay_valid, model_valid=h.model_valid)
