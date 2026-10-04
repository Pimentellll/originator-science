"""Adapter exposing the canonical Binder predictive model to the particle belief.

Pure delegation: every likelihood, sample and redesign comes from
``BinderPredictiveModel``. This module only maps particle rows to the model's
caller-owned ``BinderHypothesis`` values and back; it contains no assay
equations of its own.
"""

from __future__ import annotations

import numpy as np

from mirage.belief.schema import BINDER_SCHEMA_PROVISIONAL, LatentSchema
from mirage.core.contracts import ScientificAction, ScientificObservation
from mirage.environments.binder.predictive import BinderHypothesis, BinderPredictiveModel

_BOOL_FACTORS = ("functional_epitope", "assay_valid", "model_valid")
_FIELDS = (
    "stability",
    "monomer_fraction",
    "log_kd",
    "log_koff",
    "functional_epitope",
    "developability_liability",
    "assay_valid",
    "model_valid",
)


class BinderParticleModel:
    """ParticlePredictiveModel backed by the environment's public predictive model."""

    def __init__(
        self,
        model: BinderPredictiveModel | None = None,
        schema: LatentSchema = BINDER_SCHEMA_PROVISIONAL,
    ) -> None:
        missing = [f for f in _FIELDS if f not in schema.factors]
        if missing:
            raise ValueError(f"schema lacks BinderHypothesis fields {missing}")
        self.model = model or BinderPredictiveModel()
        self.schema = schema
        self._cols = [schema.index(f) for f in _FIELDS]
        self._cache_key: tuple | None = None
        self._cache: list[BinderHypothesis] = []

    def to_hypothesis(self, row: np.ndarray) -> BinderHypothesis:
        v = dict(zip(_FIELDS, (float(row[c]) for c in self._cols)))
        for f in _BOOL_FACTORS:
            v[f] = v[f] > 0.5
        return BinderHypothesis(**v)

    def to_row(self, h: BinderHypothesis) -> np.ndarray:
        row = np.empty(self.schema.dim)
        for f, c in zip(_FIELDS, self._cols):
            row[c] = float(getattr(h, f))
        return row

    def sample_observation(
        self, particle: np.ndarray, action: ScientificAction, rng: np.random.Generator
    ) -> ScientificObservation:
        return self.model.sample_observation(self.to_hypothesis(particle), action, rng)

    def _hypotheses(self, particles: np.ndarray) -> list[BinderHypothesis]:
        """Row -> hypothesis conversion, cached for the most recent particle array
        (EIG evaluates many observations against the same particles)."""
        key = (particles.shape, hash(particles.tobytes()))
        if key != self._cache_key:
            self._cache = [self.to_hypothesis(r) for r in particles]
            self._cache_key = key
        return self._cache

    def log_likelihood(
        self, observation: ScientificObservation, particles: np.ndarray, action: ScientificAction
    ) -> np.ndarray:
        ll = self.model.log_likelihood
        return np.array([ll(observation, h, action) for h in self._hypotheses(particles)])

    def redesign(
        self, particles: np.ndarray, action: ScientificAction, rng: np.random.Generator
    ) -> np.ndarray:
        return np.array(
            [self.to_row(self.model.redesign(self.to_hypothesis(r), action, rng)) for r in particles]
        )
