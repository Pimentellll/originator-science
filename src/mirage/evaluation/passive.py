"""HIDDEN: the PassiveBayes reference classifier (DESIGN §16.2, GATE0_SPEC §5).

Statistic s = log(mean passive reading at t = 13..18 h). Class-conditional densities are
200-bin histograms (pooled range, add-one smoothing) of s over simulated passive histories
from the ``passive_reference`` seed block. Uses the scenario prior only, never an episode's
hidden config.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from mirage.assay.od_reader import read
from mirage.biology.conditions import Condition
from mirage.biology.growth import richards
from mirage.config import SCENARIO_STREAM, ScenarioPrior

PASSIVE_STREAM = 1
LATE_TIMES_H = (13, 14, 15, 16, 17, 18)
N_BINS = 200
REFERENCE_SEEDS = range(1_000_000, 1_200_000)


def late_statistic(readings: Sequence[float] | NDArray[np.float64]) -> NDArray[np.float64]:
    """s = log of the mean passive reading at t = 13..18 h; accepts (19,) or (m, 19) arrays."""
    y = np.asarray(readings, dtype=np.float64)
    late = y[..., LATE_TIMES_H[0] : LATE_TIMES_H[-1] + 1].mean(axis=-1)
    if np.any(late <= 0):
        raise ValueError("late passive mean must be positive")
    return np.log(late)


def _loguniform(u: NDArray[np.float64], lo: float, hi: float) -> NDArray[np.float64]:
    return np.exp(math.log(lo) + u * (math.log(hi) - math.log(lo)))


def simulate_passive(
    prior: ScenarioPrior, seeds: Sequence[int], condition: Condition | str
) -> NDArray[np.float64]:
    """Passive histories (len(seeds), 19) for ``condition``, as ``LabEnvironment`` produces them.

    Same streams and sampling order as ``config.sample_episode`` and DESIGN §7, vectorised.
    """
    condition = Condition(condition)
    seeds = list(seeds)
    u = np.empty((len(seeds), 4))
    z = np.empty((len(seeds), len(prior.passive_times_h)))
    for i, seed in enumerate(seeds):
        u[i] = np.random.default_rng(np.random.SeedSequence([seed, SCENARIO_STREAM])).random(4)
        z[i] = np.random.default_rng(np.random.SeedSequence([seed, PASSIVE_STREAM])).standard_normal(
            z.shape[1]
        )
    s = _loguniform(u[:, 0], *prior.s_odeq_loguniform)
    r_lo, r_hi = prior.r_per_h_uniform
    r = r_lo + u[:, 1] * (r_hi - r_lo)
    x0 = _loguniform(u[:, 2], *prior.x0_odeq_loguniform)
    lo, hi = prior.kappa_uniform if condition is Condition.BIOLOGICAL_PLATEAU else prior.lambda_uniform
    k = (lo + u[:, 3] * (hi - lo)) * s
    t = np.asarray(prior.passive_times_h, dtype=np.float64)
    out = np.empty_like(z)
    for i in range(len(seeds)):
        x = richards(t, k_odeq=k[i], r_per_h=r[i], x0_odeq=x0[i], nu=prior.nu)
        out[i] = read(x, _Fixed(z[i]), s_odeq=s[i], n=prior.n, sigma_abs=prior.sigma_abs,
                      sigma_rel=prior.sigma_rel)
    return out


class _Fixed:
    """Stands in for a Generator so ``read`` consumes pre-drawn normals in element order."""

    def __init__(self, z: NDArray[np.float64]) -> None:
        self._z = z

    def standard_normal(self, shape: tuple[int, ...]) -> NDArray[np.float64]:
        return self._z.reshape(shape)


@dataclass(frozen=True)
class PassiveReference:
    """Smoothed class-conditional densities of the late statistic."""

    edges: NDArray[np.float64]
    density_bp: NDArray[np.float64]
    density_ma: NDArray[np.float64]
    n_per_condition: int

    def p_growth_continued(self, readings: Sequence[float]) -> float:
        """p = h_MA / (h_BP + h_MA) at the bin of s; values outside the range use the end bins."""
        s = float(late_statistic(readings))
        b = int(np.clip(np.searchsorted(self.edges, s, side="right") - 1, 0, N_BINS - 1))
        h_bp, h_ma = self.density_bp[b], self.density_ma[b]
        return float(h_ma / (h_bp + h_ma))

    def classify(self, readings: Sequence[float]) -> tuple[str, float]:
        """(label, p): the larger density wins; a tie is GROWTH_STOPPED."""
        p = self.p_growth_continued(readings)
        return ("GROWTH_CONTINUED" if p > 0.5 else "GROWTH_STOPPED"), p


def build_reference(
    prior: ScenarioPrior, seeds: Sequence[int] = REFERENCE_SEEDS
) -> PassiveReference:
    """Simulate ``len(seeds)`` passive histories per condition and histogram s (DESIGN §16.2)."""
    s_bp = late_statistic(simulate_passive(prior, seeds, Condition.BIOLOGICAL_PLATEAU))
    s_ma = late_statistic(simulate_passive(prior, seeds, Condition.MEASUREMENT_ARTIFACT))
    lo = min(s_bp.min(), s_ma.min())
    hi = max(s_bp.max(), s_ma.max())
    edges = np.linspace(lo, hi, N_BINS + 1)
    c_bp, _ = np.histogram(s_bp, bins=edges)
    c_ma, _ = np.histogram(s_ma, bins=edges)
    n = len(s_bp)
    return PassiveReference(
        edges=edges,
        density_bp=(c_bp + 1) / (n + N_BINS),
        density_ma=(c_ma + 1) / (n + N_BINS),
        n_per_condition=n,
    )
