"""Interface between the particle belief and an environment's public predictive model.

The belief never simulates assays itself. Environments publish p(observation |
hypothetical particle, action) and a redesign transition; this protocol is the
vectorised-over-particles view of that public model.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

from mirage.belief.schema import LatentSchema
from mirage.core.contracts import ScientificAction, ScientificObservation


class ParticlePredictiveModel(Protocol):
    schema: LatentSchema

    def sample_observation(
        self, particle: np.ndarray, action: ScientificAction, rng: np.random.Generator
    ) -> ScientificObservation:
        """Draw y ~ p(y | z, a) for one hypothetical particle row."""
        ...

    def log_likelihood(
        self, observation: ScientificObservation, particles: np.ndarray, action: ScientificAction
    ) -> np.ndarray:
        """log p(y | z_i, a) for every row of an (n, dim) particle array (-inf allowed)."""
        ...

    def redesign(
        self, particles: np.ndarray, action: ScientificAction, rng: np.random.Generator
    ) -> np.ndarray:
        """Push each parent row through the public redesign transition p(z' | z, a)."""
        ...
