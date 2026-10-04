"""Seeded particle posterior over factorised latent scientific worlds.

The engine is observation-model agnostic: it consumes per-particle log
likelihoods log p(y | z_i, a) and public transition kernels. It never reads
environment state; the only inputs are the prior, those likelihood vectors and
those kernels.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol

import numpy as np

from mirage.belief.resampling import RESAMPLERS
from mirage.belief.schema import FAILURE_FIELDS, LatentSchema
from mirage.belief.summary import BeliefSummary


class DegenerateBeliefError(ValueError):
    """Every particle has zero likelihood for the supplied evidence."""


class Prior(Protocol):
    """Public prior over latent worlds: returns an (n, dim) array."""

    def sample(self, rng: np.random.Generator, n: int) -> np.ndarray: ...


class IndependentPrior:
    """Prior with independent factors, one sampler ``f(rng, n) -> (n,)`` each."""

    def __init__(self, schema: LatentSchema, samplers: Mapping[str, Callable[[np.random.Generator, int], np.ndarray]]):
        missing = [f for f in schema.factors if f not in samplers]
        if missing:
            raise ValueError(f"no sampler for factors {missing}")
        self._schema = schema
        self._samplers = dict(samplers)

    def sample(self, rng: np.random.Generator, n: int) -> np.ndarray:
        return np.column_stack([np.asarray(self._samplers[f](rng, n), dtype=float) for f in self._schema.factors])


# p(z' | z): maps (n, dim) parent particles to (n, dim) child particles.
TransitionKernel = Callable[[np.ndarray, np.random.Generator], np.ndarray]


@dataclass(frozen=True)
class UpdateInfo:
    ess_before: float  # prior to the update
    ess_weighted: float  # after reweighting, before any resampling (the trigger statistic)
    ess_after: float
    resampled: bool
    log_evidence: float  # log of the predictive probability of the evidence under the belief


def logsumexp(x: np.ndarray) -> float:
    m = np.max(x)
    if not np.isfinite(m):
        return float(m)
    return float(m + np.log(np.sum(np.exp(x - m))))


class ParticleBelief:
    """Weighted particle approximation of the latent posterior."""

    def __init__(
        self,
        schema: LatentSchema,
        particles: np.ndarray,
        log_weights: np.ndarray | None = None,
        *,
        seed: int = 0,
        ess_threshold: float = 0.5,
        resampling: str = "systematic",
    ) -> None:
        particles = np.array(particles, dtype=float)
        if particles.ndim != 2 or particles.shape[1] != schema.dim or particles.shape[0] < 1:
            raise ValueError(f"particles must have shape (n, {schema.dim}), got {particles.shape}")
        if not np.all(np.isfinite(particles)):
            raise ValueError("particles must be finite")
        if resampling not in RESAMPLERS:
            raise ValueError(f"unknown resampling scheme {resampling!r}")
        if not 0.0 <= ess_threshold <= 1.0:
            raise ValueError("ess_threshold is a fraction of n and must lie in [0, 1]")
        n = particles.shape[0]
        self.schema = schema
        self._particles = particles
        self.ess_threshold = ess_threshold
        self.resampling = resampling
        self._rng = np.random.default_rng(seed)
        if log_weights is None:
            self._log_w = np.full(n, -np.log(n))
        else:
            lw = np.array(log_weights, dtype=float)
            if lw.shape != (n,) or np.any(np.isnan(lw)) or np.any(lw == np.inf):
                raise ValueError("log_weights must be a length-n array without NaN/+inf")
            self._log_w = self._normalise(lw)

    @classmethod
    def from_prior(
        cls, schema: LatentSchema, prior: Prior, n: int = 512, seed: int = 0, **kwargs
    ) -> "ParticleBelief":
        """Draw n particles with uniform weights. Prior draws use a stream
        independent of the belief's resampling stream."""
        particles = prior.sample(np.random.default_rng([seed, 0]), n)
        return cls(schema, particles, seed=seed, **kwargs)

    # -- weights ---------------------------------------------------------

    @staticmethod
    def _normalise(log_w: np.ndarray) -> np.ndarray:
        z = logsumexp(log_w)
        if not np.isfinite(z):
            raise DegenerateBeliefError("all particle weights are zero")
        return log_w - z

    @property
    def n(self) -> int:
        return self._particles.shape[0]

    @property
    def log_weights(self) -> np.ndarray:
        return self._log_w.copy()

    @property
    def weights(self) -> np.ndarray:
        w = np.exp(self._log_w)
        return w / w.sum()

    @property
    def effective_sample_size(self) -> float:
        return float(1.0 / np.sum(self.weights**2))

    @property
    def particles(self) -> np.ndarray:
        """Posterior particles (read-only view). Internal to the belief engine
        and the EIG policy; never serialised into a BeliefSummary."""
        view = self._particles.view()
        view.flags.writeable = False
        return view

    # -- inference -------------------------------------------------------

    def update(self, log_likelihood: np.ndarray, *, resample: bool | None = None) -> UpdateInfo:
        """Bayes update w'_i ∝ w_i p(y | z_i, a) in log space.

        ``resample=None`` resamples iff ESS < ess_threshold * n; True/False force it.
        Raises DegenerateBeliefError, leaving the belief unchanged, if the evidence
        has zero likelihood under every particle.
        """
        ll = np.asarray(log_likelihood, dtype=float)
        if ll.shape != (self.n,):
            raise ValueError(f"log_likelihood must have shape ({self.n},), got {ll.shape}")
        if np.any(np.isnan(ll)) or np.any(ll == np.inf):
            raise ValueError("log_likelihood must not contain NaN or +inf")
        ess_before = self.effective_sample_size
        joint = self._log_w + ll
        log_evidence = logsumexp(joint)
        if not np.isfinite(log_evidence):
            raise DegenerateBeliefError("evidence has zero likelihood under every particle")
        self._log_w = joint - log_evidence
        ess_weighted = self.effective_sample_size
        do_resample = (ess_weighted < self.ess_threshold * self.n) if resample is None else resample
        if do_resample:
            self.resample()
        return UpdateInfo(ess_before, ess_weighted, self.effective_sample_size, do_resample, log_evidence)

    def resample(self, method: str | None = None) -> None:
        """Replace the weighted set by an equally weighted one (seeded)."""
        scheme = RESAMPLERS[method or self.resampling]
        idx = scheme(self.weights, self._rng)
        self._particles = self._particles[idx]
        self._log_w = np.full(self.n, -np.log(self.n))

    def transition(self, kernel: TransitionKernel) -> None:
        """Propagate each particle through a public transition kernel p(z' | z).

        Used after redesign: the belief becomes a belief about the *new*
        candidate, obtained by pushing the parent posterior through the public
        redesign model. Weights are retained (the child inherits parent evidence
        only through the kernel); old latents are not carried over unchanged.
        """
        child = np.asarray(kernel(self.particles.copy(), self._rng), dtype=float)
        if child.shape != self._particles.shape or not np.all(np.isfinite(child)):
            raise ValueError("transition kernel must return finite particles of unchanged shape")
        self._particles = child

    def copy(self) -> "ParticleBelief":
        """Independent deep copy including RNG state (for hypothetical updates)."""
        return copy.deepcopy(self)

    # -- summaries -------------------------------------------------------

    def failure_indicators(self) -> np.ndarray:
        """(n, 8) boolean matrix, columns ordered as FAILURE_FIELDS."""
        cols = []
        for name in FAILURE_FIELDS:
            rule = self.schema.failure_rules[name]
            x = self._particles[:, self.schema.index(rule.factor)]
            cols.append(x < rule.threshold if rule.direction == "below" else x > rule.threshold)
        return np.column_stack(cols)

    def failure_probabilities(self) -> dict[str, float]:
        """Posterior mass of each (non-exclusive) failure rule."""
        p = self.weights @ self.failure_indicators().astype(float)
        return {name: float(np.clip(v, 0.0, 1.0)) for name, v in zip(FAILURE_FIELDS, p)}

    def pattern_distribution(self) -> np.ndarray:
        """Posterior over the 2**8 joint failure patterns (compound-aware)."""
        bits = 1 << np.arange(len(FAILURE_FIELDS))
        codes = self.failure_indicators().astype(np.int64) @ bits
        return np.bincount(codes, weights=self.weights, minlength=1 << len(FAILURE_FIELDS))

    def mechanism_entropy(self) -> float:
        """Shannon entropy (nats) of the joint failure-pattern distribution."""
        p = self.pattern_distribution()
        p = p[p > 0]
        return float(max(0.0, -np.sum(p * np.log(p))))

    def summary(self) -> BeliefSummary:
        w = self.weights
        means: dict[str, float] = {}
        variances: dict[str, float] = {}
        for factor in self.schema.summary_factors:
            x = self._particles[:, self.schema.index(factor)]
            mu = float(w @ x)
            means[factor] = mu
            variances[factor] = float(max(0.0, w @ (x - mu) ** 2))
        return BeliefSummary(
            **self.failure_probabilities(),
            posterior_entropy=self.mechanism_entropy(),
            continuous_means=means,
            continuous_variances=variances,
            effective_sample_size=self.effective_sample_size,
        )
