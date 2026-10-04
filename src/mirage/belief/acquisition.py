"""Monte Carlo expected information gain over the failure-marginal entropy.

    EIG(a) = H(b_t) - E_y[ H(b_{t+1}) ]

H is ``ParticleBelief.mechanism_entropy`` (the same value reported as
``BeliefSummary.posterior_entropy``). y is drawn from the belief's own
predictive distribution: a source particle is chosen by seeded systematic
resampling of the posterior weights and an observation is sampled from the
environment's PUBLIC predictive model at that hypothetical particle. Each y is
pushed through the exact Bayes update over all particles. No ground truth is
consulted; the source particle is only a hypothetical world.

Finite-particle bias. A sharp likelihood collapses the reweighted particle set
onto the source particle itself, which makes the estimated entropy after the
update spuriously small and EIG spuriously large (at N=512 the SPR estimate was
about 2x its converged value). Two measures keep the estimate usable:

* the entropy is a sum of per-mechanism binary entropies, whose plug-in bias is
  O(1/ESS) per term rather than O(#patterns/ESS) for the joint pattern entropy;
* the likelihood is tempered by tau <= 1 (found by bisection on the stored
  log-likelihood matrix) so that the mean reweighted ESS stays above
  ``min_posterior_ess``. This equals EIG for an equivalently noisier assay: a
  conservative estimate at the resolution the particle set can support. tau is
  reported so callers can see when it bound.

One step only: this is deliberately myopic.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from mirage.belief.particles import ParticleBelief, binary_entropy
from mirage.belief.predictive import ParticlePredictiveModel
from mirage.belief.resampling import systematic_resample
from mirage.core.contracts import ScientificAction


@dataclass(frozen=True)
class EIGEstimate:
    eig: float  # nats
    tempering: float  # tau in (0, 1]; 1.0 means the exact likelihood was used
    mean_posterior_ess: float  # mean ESS of the hypothetical posteriors at that tau


def sample_sources(belief: ParticleBelief, rng: np.random.Generator, n_samples: int) -> np.ndarray:
    """Hypothetical source particles (seeded, low-variance); shareable across actions."""
    return systematic_resample(belief.weights, rng, size=n_samples)


def _posteriors(log_w: np.ndarray, ll: np.ndarray, tau: float) -> np.ndarray:
    joint = log_w + np.where(np.isfinite(ll), tau * ll, -np.inf)
    top = joint.max(axis=1, keepdims=True)
    post = np.exp(joint - top)
    return post / post.sum(axis=1, keepdims=True)


def _mean_ess(post: np.ndarray) -> float:
    return float(np.mean(1.0 / np.sum(post**2, axis=1)))


def expected_information_gain(
    belief: ParticleBelief,
    model: ParticlePredictiveModel,
    action: ScientificAction,
    *,
    n_samples: int,
    rng: np.random.Generator,
    source_indices: np.ndarray | None = None,
    min_posterior_ess: float = 10.0,
) -> EIGEstimate:
    """One-step MC estimate of EIG(action). Never mutates ``belief``.

    ``source_indices`` lets callers share the same hypothetical source particles
    across actions (common random numbers) so action scores are comparable.
    """
    if n_samples < 1:
        raise ValueError("n_samples must be >= 1")
    particles = belief.particles
    if source_indices is None:
        source_indices = sample_sources(belief, rng, n_samples)

    ll = np.empty((len(source_indices), belief.n))
    for m, j in enumerate(source_indices):
        y = model.sample_observation(particles[j], action, rng)
        ll[m] = model.log_likelihood(y, particles, action)
    ok = np.isfinite(ll.max(axis=1))  # a sample must be possible under at least one particle
    if not ok.any():
        return EIGEstimate(0.0, 1.0, belief.effective_sample_size)
    ll = ll[ok]

    log_w = belief.log_weights
    target = min(min_posterior_ess, 0.5 * belief.effective_sample_size)
    tau = 1.0
    if _mean_ess(_posteriors(log_w, ll, 1.0)) < target:
        lo, hi = 0.0, 1.0
        for _ in range(30):
            mid = 0.5 * (lo + hi)
            if _mean_ess(_posteriors(log_w, ll, mid)) >= target:
                lo = mid
            else:
                hi = mid
        tau = lo
    post = _posteriors(log_w, ll, tau)
    indicators = belief.failure_indicators().astype(float)
    h_after = binary_entropy(post @ indicators).sum(axis=1)
    return EIGEstimate(float(belief.mechanism_entropy() - h_after.mean()), tau, _mean_ess(post))
