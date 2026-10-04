"""Seeded low-variance resampling schemes over normalised weights."""

from __future__ import annotations

import numpy as np


def _inverse_cdf(weights: np.ndarray, positions: np.ndarray) -> np.ndarray:
    cdf = np.cumsum(weights)
    cdf /= cdf[-1]  # guard against round-off so the last bin always closes
    return np.minimum(np.searchsorted(cdf, positions, side="right"), len(weights) - 1)


def systematic_resample(weights: np.ndarray, rng: np.random.Generator, size: int | None = None) -> np.ndarray:
    """One uniform offset shared by all strata; lowest variance, O(N)."""
    n = size if size is not None else len(weights)
    positions = (rng.random() + np.arange(n)) / n
    return _inverse_cdf(weights, positions)


def stratified_resample(weights: np.ndarray, rng: np.random.Generator, size: int | None = None) -> np.ndarray:
    """An independent uniform offset in each stratum."""
    n = size if size is not None else len(weights)
    positions = (rng.random(n) + np.arange(n)) / n
    return _inverse_cdf(weights, positions)


RESAMPLERS = {"systematic": systematic_resample, "stratified": stratified_resample}
