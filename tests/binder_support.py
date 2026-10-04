"""Shared test support: a test-only prior and a harness that plays the environment.

The harness holds a 'true' hypothesis ONLY to generate observations for tests;
policies and beliefs under test never see it. The prior here is a test fixture,
not the environment's scenario prior.
"""

from __future__ import annotations

import numpy as np

from mirage.belief import (
    BINDER_SCHEMA_PROVISIONAL as SCHEMA,
    ConditionedPrior,
    IndependentPrior,
    MixturePrior,
    ParticleBelief,
    bernoulli,
    uniform,
)
from mirage.belief.binder import BinderParticleModel
from mirage.core.contracts import ActionType as A, ScientificAction, ScientificObservation

MODEL = BinderParticleModel()

# Test-only priors (tractable densities, so resample-move is exercised). Not the
# environment's scenario prior.
_PRIOR = IndependentPrior(
    SCHEMA,
    {
        "stability": uniform(0, 1),
        "monomer_fraction": uniform(0.4, 1),
        "log_kd": uniform(-10, -5),
        "log_koff": uniform(-5, 0),
        "functional_epitope": bernoulli(0.5),
        "developability_liability": uniform(0, 1),
        "assay_valid": bernoulli(0.5),
        "model_valid": bernoulli(0.5),
    },
)

# A molecule that is good on every assay-visible axis (strictly inside the non-failure
# side of every placeholder threshold); assay/model validity uncertain.
_GOOD = IndependentPrior(
    SCHEMA,
    {
        "stability": uniform(0.7, 1),
        "monomer_fraction": uniform(0.9, 1),
        "log_kd": uniform(-10, -8),
        "log_koff": uniform(-5, -3),
        "functional_epitope": bernoulli(1.0),
        "developability_liability": uniform(0, 0.3),
        "assay_valid": bernoulli(0.5),
        "model_valid": bernoulli(0.5),
    },
)


def _any_failure(z: np.ndarray) -> np.ndarray:
    return ParticleBelief(SCHEMA, z).failure_indicators().any(axis=1)


# 60% broad worlds + 40% good-molecule worlds, conditioned on 'the campaign started from a
# downstream failure' (worlds where no failure rule fires are excluded).
_CONDITIONED = ConditionedPrior(MixturePrior([(0.6, _PRIOR), (0.4, _GOOD)]), _any_failure)


def act(t: A, cid: str = "c0") -> ScientificAction:
    return ScientificAction(action_type=t, candidate_id=cid)


def obs(t: A, quality: str = "nominal", cid: str = "c0", **measurements: float) -> ScientificObservation:
    return ScientificObservation(action_type=t, candidate_id=cid, measurements=measurements, quality=quality)


def make_belief(n: int = 512, seed: int = 0, conditioned: bool = False, **kw) -> ParticleBelief:
    prior = _CONDITIONED if conditioned else _PRIOR
    return ParticleBelief.from_prior(SCHEMA, prior, n=n, seed=seed, **kw)
