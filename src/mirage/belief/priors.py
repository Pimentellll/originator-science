"""Public prior distributions over latent worlds.

A prior always provides ``sample``. When it can also evaluate ``log_prob``
(unnormalised log density, ``-inf`` outside the support) the belief can
rejuvenate resampled particles with MCMC moves that leave the posterior
invariant; without it the belief falls back to plain resampling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, Sequence

import numpy as np

from mirage.belief.schema import LatentSchema


class Prior(Protocol):
    def sample(self, rng: np.random.Generator, n: int) -> np.ndarray:
        """Draw an (n, dim) array of latent worlds."""
        ...


@dataclass(frozen=True)
class Factor:
    """One latent factor's marginal: a sampler and (optionally) a log density."""

    sample: Callable[[np.random.Generator, int], np.ndarray]
    log_prob: Callable[[np.ndarray], np.ndarray] | None = None


def uniform(lo: float, hi: float) -> Factor:
    def log_prob(x: np.ndarray) -> np.ndarray:
        return np.where((x >= lo) & (x <= hi), -np.log(hi - lo), -np.inf)

    return Factor(lambda r, n: r.uniform(lo, hi, n), log_prob)


def bernoulli(p: float) -> Factor:
    """Binary 0/1 factor with P(1) = p."""

    def log_prob(x: np.ndarray) -> np.ndarray:
        with np.errstate(divide="ignore"):
            return np.where(x == 1.0, np.log(p), np.where(x == 0.0, np.log1p(-p) if p < 1 else -np.inf, -np.inf))

    return Factor(lambda r, n: (r.random(n) < p).astype(float), log_prob)


class IndependentPrior:
    """Independent factors. Each entry is a ``Factor`` or a bare sampler
    ``f(rng, n) -> (n,)`` (no density, so no rejuvenation)."""

    def __init__(self, schema: LatentSchema, factors: Mapping[str, Factor | Callable]):
        missing = [f for f in schema.factors if f not in factors]
        if missing:
            raise ValueError(f"no distribution for factors {missing}")
        self._schema = schema
        self._factors = {f: x if isinstance(x, Factor) else Factor(x) for f, x in factors.items()}
        if all(self._factors[f].log_prob is not None for f in schema.factors):
            self.log_prob = self._log_prob  # exposed only when every marginal has a density

    def sample(self, rng: np.random.Generator, n: int) -> np.ndarray:
        return np.column_stack([np.asarray(self._factors[f].sample(rng, n), dtype=float) for f in self._schema.factors])

    def _log_prob(self, z: np.ndarray) -> np.ndarray:
        return sum(self._factors[f].log_prob(z[:, i]) for i, f in enumerate(self._schema.factors))


class MixturePrior:
    """Finite mixture of priors; has a density iff every component does."""

    def __init__(self, components: Sequence[tuple[float, Prior]]):
        w = np.array([c[0] for c in components], dtype=float)
        if np.any(w <= 0):
            raise ValueError("mixture weights must be positive")
        self._w = w / w.sum()
        self._priors = [c[1] for c in components]
        if all(hasattr(p, "log_prob") for p in self._priors):
            self.log_prob = self._log_prob

    def sample(self, rng: np.random.Generator, n: int) -> np.ndarray:
        which = rng.choice(len(self._priors), size=n, p=self._w)
        out = None
        for k, prior in enumerate(self._priors):
            draw = prior.sample(rng, n)
            if out is None:
                out = np.empty_like(draw)
            out[which == k] = draw[which == k]
        return out

    def _log_prob(self, z: np.ndarray) -> np.ndarray:
        parts = np.stack([np.log(w) + p.log_prob(z) for w, p in zip(self._w, self._priors)])
        top = parts.max(axis=0)
        safe = np.where(np.isfinite(top), top, 0.0)
        with np.errstate(divide="ignore"):
            return np.where(np.isfinite(top), safe + np.log(np.exp(parts - safe).sum(axis=0)), -np.inf)


class ConditionedPrior:
    """``base`` restricted to worlds where ``predicate(z) -> bool mask`` holds
    (rejection sampling; unnormalised density), e.g. 'the campaign began from a
    downstream failure'."""

    def __init__(self, base: Prior, predicate: Callable[[np.ndarray], np.ndarray]):
        self._base, self._predicate = base, predicate
        if hasattr(base, "log_prob"):
            self.log_prob = self._log_prob

    def sample(self, rng: np.random.Generator, n: int) -> np.ndarray:
        kept: list[np.ndarray] = []
        count = 0
        for _ in range(1000):
            z = self._base.sample(rng, 4 * n)
            z = z[self._predicate(z)]
            kept.append(z)
            count += len(z)
            if count >= n:
                return np.vstack(kept)[:n]
        raise RuntimeError("predicate rejects (almost) every prior draw")

    def _log_prob(self, z: np.ndarray) -> np.ndarray:
        return np.where(self._predicate(z), self._base.log_prob(z), -np.inf)
