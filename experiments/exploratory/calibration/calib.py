"""Calibration statistics and the late-data reference posterior (exploratory; see REGISTRATION.md).

Pure functions on arrays. Nothing here reads or writes run records.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

BIN_EDGES = (0.0, 0.1, 0.3, 0.7, 0.9, 1.0)
LOG_LOSS_EPS = 1e-6
BOOTSTRAP_B = 10_000
BOOTSTRAP_SEED = 20261004
LATE_POSTERIOR_MIN_T_H = 14
GRID_N_LOG_S = 4000
GRID_N_RATIO = 400


def bin_index(p: ArrayLike, edges: Sequence[float] = BIN_EDGES) -> NDArray[np.int64]:
    """Bin of each p: left-closed bins, the last bin closed at the top edge."""
    p = np.asarray(p, dtype=np.float64)
    if np.any((p < edges[0]) | (p > edges[-1])):
        raise ValueError("p outside the bin range")
    return np.minimum(np.searchsorted(edges, p, side="right") - 1, len(edges) - 2)


def _groups(p: NDArray[np.float64], edges: Sequence[float] | None) -> NDArray[np.int64]:
    """Bin labels; ``edges=None`` means one group per distinct forecast value."""
    if edges is None:
        return np.unique(p, return_inverse=True)[1].reshape(-1)
    return bin_index(p, edges)


def reliability_table(p: ArrayLike, y: ArrayLike, edges: Sequence[float] = BIN_EDGES) -> list[dict]:
    """Per non-empty bin: n, mean forecast, observed frequency (with its count)."""
    p = np.asarray(p, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    b = bin_index(p, edges)
    rows = []
    for i in range(len(edges) - 1):
        m = b == i
        if m.any():
            rows.append({"bin": [edges[i], edges[i + 1]], "n": int(m.sum()),
                         "mean_p": float(p[m].mean()), "k": int(y[m].sum()),
                         "freq": float(y[m].mean())})
    return rows


def murphy(p: ArrayLike, y: ArrayLike, edges: Sequence[float] | None = BIN_EDGES) -> dict[str, float]:
    """Brier = REL - RES + UNC + residual (residual = within-bin term; 0 when edges=None)."""
    p = np.asarray(p, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    g = _groups(p, edges)
    n = len(p)
    obar = y.mean()
    rel = res = 0.0
    for k in np.unique(g):
        m = g == k
        w = m.sum() / n
        rel += w * (p[m].mean() - y[m].mean()) ** 2
        res += w * (y[m].mean() - obar) ** 2
    unc = obar * (1 - obar)
    bs = float(np.mean((p - y) ** 2))
    return {"brier": bs, "rel": float(rel), "res": float(res), "unc": float(unc),
            "residual": float(bs - (rel - res + unc))}


def ece(p: ArrayLike, y: ArrayLike, edges: Sequence[float] = BIN_EDGES) -> float:
    p = np.asarray(p, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    b = bin_index(p, edges)
    return float(sum((b == k).mean() * abs(p[b == k].mean() - y[b == k].mean())
                     for k in np.unique(b)))


def log_loss(p: ArrayLike, y: ArrayLike, eps: float = LOG_LOSS_EPS) -> tuple[float, int]:
    """Mean negative log likelihood in nats, and the number of forecasts clipped."""
    p = np.asarray(p, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    q = np.clip(p, eps, 1 - eps)
    ll = -(y * np.log(q) + (1 - y) * np.log(1 - q))
    return float(ll.mean()), int(np.sum(q != p))


def stratified_indices(strata: ArrayLike, b: int = BOOTSTRAP_B, seed: int = BOOTSTRAP_SEED) -> NDArray[np.int64]:
    """(b, N) resample indices; each stratum is resampled with replacement within itself."""
    strata = np.asarray(strata)
    rng = np.random.default_rng(seed)
    out = np.empty((b, len(strata)), dtype=np.int64)
    col = 0
    for s in np.unique(strata):
        pos = np.flatnonzero(strata == s)
        out[:, col:col + len(pos)] = pos[rng.integers(0, len(pos), size=(b, len(pos)))]
        col += len(pos)
    return out


def percentile_ci(samples: ArrayLike) -> list[float] | None:
    s = np.asarray(samples, dtype=np.float64)
    s = s[np.isfinite(s)]
    if s.size == 0:
        return None
    return [float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))]


def auroc(score: ArrayLike, label: ArrayLike) -> float:
    """P(score of a positive > score of a negative), ties count 1/2; NaN if a class is empty."""
    score = np.asarray(score, dtype=np.float64)
    label = np.asarray(label, dtype=bool)
    pos, neg = score[label], score[~label]
    if pos.size == 0 or neg.size == 0:
        return math.nan
    diff = pos[:, None] - neg[None, :]
    return float(((diff > 0) + 0.5 * (diff == 0)).mean())


def poisson_binomial_sf(probs: ArrayLike, k: int) -> float:
    """P(at least k successes) for independent Bernoulli(probs), by exact recursion."""
    dist = np.zeros(1)
    dist[0] = 1.0
    for q in np.asarray(probs, dtype=np.float64):
        dist = np.concatenate([dist * (1 - q), [0.0]]) + np.concatenate([[0.0], dist * q])
    return float(dist[k:].sum())


def assay_response(x: ArrayLike, s: ArrayLike, n: float) -> NDArray[np.float64]:
    """f(x) = x [1 + (x/S)^n]^(-1/n); same formula as mirage.assay.od_reader.response."""
    x = np.asarray(x, dtype=np.float64)
    return x * (1.0 + (x / s) ** n) ** (-1.0 / n)


def _log_marginal(obs_d: NDArray, obs_y: NDArray, log_s: NDArray, ratio: NDArray,
                  n: float, sigma_abs: float, sigma_rel: float) -> float:
    """log of the prior-mean likelihood over a uniform (log S, ratio) grid."""
    s = np.exp(log_s)[:, None, None]
    k = ratio[None, :, None] * s
    mu = assay_response(k / obs_d[None, None, :], s, n)
    sd = sigma_abs + sigma_rel * mu
    ll = (-0.5 * ((obs_y[None, None, :] - mu) / sd) ** 2 - np.log(sd)
          - 0.5 * math.log(2 * math.pi)).sum(axis=-1)
    mx = ll.max()
    return float(mx + math.log(np.exp(ll - mx).mean()))


def _midpoints(lo: float, hi: float, m: int) -> NDArray[np.float64]:
    return lo + (np.arange(m) + 0.5) * (hi - lo) / m


def late_posterior(obs: Sequence[tuple[int, float, float]], prior: dict, *,
                   min_t_h: int = LATE_POSTERIOR_MIN_T_H, n_log_s: int = GRID_N_LOG_S,
                   n_ratio: int = GRID_N_RATIO, prior_ma: float = 0.5) -> dict:
    """P(MA | readings at t >= min_t_h), taking latent biomass = K there (REGISTRATION §6b).

    ``obs`` is (time_h, dilution, reading) per replicate; ``prior`` is the scenario-v1 JSON.
    """
    used = [(d, y) for t, d, y in obs if t >= min_t_h]
    if not used:
        raise ValueError("no readings at or after min_t_h")
    d = np.array([u[0] for u in used], dtype=np.float64)
    y = np.array([u[1] for u in used], dtype=np.float64)
    lo, hi = prior["s_odeq_loguniform"]
    log_s = _midpoints(math.log(lo), math.log(hi), n_log_s)
    kw = {"n": float(prior["n"]), "sigma_abs": float(prior["sigma_abs"]),
          "sigma_rel": float(prior["sigma_rel"])}
    lm = {}
    for cond, key in (("BP", "kappa_uniform"), ("MA", "lambda_uniform")):
        ratio = _midpoints(*prior[key], n_ratio)
        chunks = [_log_marginal(d, y, ls, ratio, **kw) for ls in np.array_split(log_s, 40)]
        # equal-sized chunks of a uniform grid: the overall mean is the mean of chunk means
        sizes = np.array([len(c) for c in np.array_split(log_s, 40)], dtype=np.float64)
        c = np.array(chunks) + np.log(sizes / sizes.sum())
        mx = c.max()
        lm[cond] = float(mx + math.log(np.exp(c - mx).sum()))
    log_odds = lm["MA"] - lm["BP"] + math.log(prior_ma / (1 - prior_ma))
    p_ma = 1.0 / (1.0 + math.exp(-log_odds)) if log_odds > -700 else 0.0
    return {"p_ma": p_ma, "log10_odds_ma": log_odds / math.log(10), "n_used": len(used),
            "n_dropped": len(obs) - len(used), "log_marginal": lm}


LATE_WINDOW_H = (12, 18)
PLATEAU_TIMES_H = (15, 16, 17, 18)


def corrected_plateau_ratio(passive: dict[int, float], reads: Sequence[tuple[int, float, float]],
                            late_window_h: tuple[int, int] = LATE_WINDOW_H,
                            plateau_times_h: Sequence[int] = PLATEAU_TIMES_H) -> float | None:
    """mean(d * reading) over late diluted replicate reads / mean passive reading at 15-18 h.

    ``reads`` is (time_h, dilution, reading) per replicate. None if no late diluted read.
    """
    lo, hi = late_window_h
    c = [d * y for t, d, y in reads if lo <= t <= hi and d > 1]
    if not c:
        return None
    return float(np.mean(c) / np.mean([passive[t] for t in plateau_times_h]))


def simulate_ratio(latent_by_t: dict[int, float], design: Sequence[tuple[int, float, int]], *,
                   s_odeq: float, n: float, sigma_abs: float, sigma_rel: float, draws: int,
                   seed: int, plateau_times_h: Sequence[int] = PLATEAU_TIMES_H,
                   decimals: int = 4) -> NDArray[np.float64]:
    """Monte Carlo of ``corrected_plateau_ratio`` under one fixed hidden config.

    ``design`` is (time_h, dilution, replicates) per request; every request in it is assumed
    late and diluted. Passive plateau readings and diluted reads are both redrawn with the
    assay noise model y = round(f(x) + (sigma_abs + sigma_rel f) z, decimals).
    """
    rng = np.random.default_rng(seed)

    def draw(x: NDArray[np.float64]) -> NDArray[np.float64]:
        mu = assay_response(x, s_odeq, n)
        z = rng.standard_normal((draws, x.size))
        return np.round(mu + (sigma_abs + sigma_rel * mu) * z, decimals)

    plateau = draw(np.array([latent_by_t[t] for t in plateau_times_h])).mean(axis=1)
    pres = np.array([latent_by_t[t] / d for t, d, r in design for _ in range(r)])
    dil = np.array([d for t, d, r in design for _ in range(r)])
    corrected = (draw(pres) * dil).mean(axis=1)
    return corrected / plateau
