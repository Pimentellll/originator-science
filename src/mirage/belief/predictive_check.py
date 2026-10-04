"""Is the current causal model able to generate the observed evidence?

Both checks use only the canonical public predictive model (``sample_observation`` and
``log_likelihood``); no second simulator, no truth.

``predictive_surprise`` (prequential, call BEFORE ``observe``)
    How surprising is this observation under the belief that existed before seeing it?
    Discrepancy T(y) = log marginal predictive probability log sum_i w_i p(y | z_i, a).
    p = P_{y_rep ~ predictive}[ T(y_rep) <= T(y_obs) ]. An observation no particle can
    generate has T = -inf and the smallest attainable p, flagged ``impossible``.

``posterior_predictive_check`` (post hoc, over the evidence a belief has absorbed)
    For each absorbed observation, T = log p(y | z, a) with z ~ posterior and
    y_rep ~ p(. | z, a): p = P[T(y_rep, z) <= T(y_obs, z)]. Standard Gelman-style check;
    conservative because the posterior was fitted to the same data, so a LOW p is strong
    evidence of misfit while a high p is only reassurance.

Small p-values mean "observations poorly explained by the current causal model"; large
ones mean "uncertain but model-consistent". Thresholds are diagnostic defaults.
"""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from mirage.belief.particles import ParticleBelief, logsumexp
from mirage.belief.predictive import ParticlePredictiveModel
from mirage.belief.resampling import systematic_resample
from mirage.core.contracts import ActionType, ScientificAction, ScientificObservation


class ObservationSurprise(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action_type: ActionType
    p_value: float = Field(ge=0.0, le=1.0)
    log_predictive: float | None  # None when no particle can generate the observation
    impossible: bool


class PredictiveCheckReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: Literal["no_evidence", "consistent", "poorly_explained"]
    observations: tuple[ObservationSurprise, ...]
    combined_p_value: float | None = None  # Fisher's method over observations
    min_p_value: float | None = None
    alpha: float = 0.01


def _fisher(p_values: list[float]) -> float:
    """Survival function of -2 sum ln p ~ chi^2 with 2k d.o.f. (closed form for even d.o.f.)."""
    k = len(p_values)
    half = -sum(math.log(max(p, 1e-300)) for p in p_values)
    term, total = 1.0, 1.0
    for j in range(1, k):
        term *= half / j
        total += term
    return float(min(1.0, math.exp(-half) * total))


def _marginal_log_predictive(log_w: np.ndarray, ll: np.ndarray) -> float:
    return logsumexp(log_w + ll)


def predictive_surprise(
    belief: ParticleBelief,
    model: ParticlePredictiveModel,
    action: ScientificAction,
    observation: ScientificObservation,
    *,
    n_samples: int = 64,
    rng: np.random.Generator,
) -> ObservationSurprise:
    """Prequential surprise of ``observation`` under ``belief``. Does not mutate the belief."""
    particles, log_w = belief.particles, belief.log_weights
    observed = _marginal_log_predictive(log_w, model.log_likelihood(observation, particles, action))
    sources = systematic_resample(belief.weights, rng, size=n_samples)
    replicated = np.array(
        [
            _marginal_log_predictive(log_w, model.log_likelihood(model.sample_observation(particles[j], action, rng), particles, action))
            for j in sources
        ]
    )
    p = (1.0 + float(np.sum(replicated <= observed))) / (n_samples + 1.0)
    impossible = not np.isfinite(observed)
    return ObservationSurprise(
        action_type=action.action_type,
        p_value=min(1.0, p if not impossible else 1.0 / (n_samples + 1.0)),
        log_predictive=None if impossible else float(observed),
        impossible=impossible,
    )


def _verdict(items: list[ObservationSurprise], alpha: float) -> PredictiveCheckReport:
    if not items:
        return PredictiveCheckReport(verdict="no_evidence", observations=(), alpha=alpha)
    ps = [i.p_value for i in items]
    combined, smallest = _fisher(ps), min(ps)
    bad = combined < alpha or smallest * len(ps) < alpha or any(i.impossible for i in items)
    return PredictiveCheckReport(
        verdict="poorly_explained" if bad else "consistent",
        observations=tuple(items),
        combined_p_value=combined,
        min_p_value=smallest,
        alpha=alpha,
    )


def summarise_surprises(items: list[ObservationSurprise], alpha: float = 0.01) -> PredictiveCheckReport:
    """Combine prequential per-observation surprises (collected before each ``observe``)."""
    return _verdict(list(items), alpha)


def posterior_predictive_check(
    belief: ParticleBelief,
    *,
    n_samples: int = 64,
    seed: int = 0,
    alpha: float = 0.01,
    model: ParticlePredictiveModel | None = None,
) -> PredictiveCheckReport:
    """Post hoc check of every observation absorbed on the current candidate."""
    rng = np.random.default_rng(seed)
    particles = belief.particles
    items: list[ObservationSurprise] = []
    models = belief.evidence_models
    for (action, observation), recorded in zip(belief.evidence, models):
        m = model or recorded
        sources = systematic_resample(belief.weights, rng, size=n_samples)
        reps = np.empty(n_samples)
        obs_t = np.empty(n_samples)
        for k, j in enumerate(sources):
            z = particles[j : j + 1]
            reps[k] = m.log_likelihood(m.sample_observation(particles[j], action, rng), z, action)[0]
            obs_t[k] = m.log_likelihood(observation, z, action)[0]
        impossible = bool(np.any(~np.isfinite(obs_t)) and np.mean(~np.isfinite(obs_t)) > 0.5)
        p = (1.0 + float(np.sum(reps <= obs_t))) / (n_samples + 1.0)
        items.append(
            ObservationSurprise(
                action_type=action.action_type,
                p_value=min(1.0, p),
                log_predictive=None if impossible else float(np.mean(obs_t[np.isfinite(obs_t)])) if np.any(np.isfinite(obs_t)) else None,
                impossible=impossible,
            )
        )
    return _verdict(items, alpha)
