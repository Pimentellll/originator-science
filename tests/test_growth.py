"""T-002 and T-003: Richards growth model (DESIGN §5.2).

The DEV-002 scenario sampler does not exist yet, so T-003 draws configurations here
from the scenario-v1 ranges in DESIGN §5.8, using a fixed-seed Generator, and also
checks the slowest-growth corner explicitly.
"""

from __future__ import annotations

import numpy as np
import pytest

from mirage.biology.growth import richards

# DESIGN §5.8 (scenario-v1)
NU = 8.0
S_RANGE = (0.5, 2.0)  # log-uniform, ODeq
KAPPA_RANGE = (0.80, 0.90)  # BIOLOGICAL_PLATEAU: K = kappa * S
R_RANGE = (0.6, 0.9)  # uniform, 1/h
X0_RANGE = (0.005, 0.02)  # log-uniform, ODeq
LATE_WINDOW_H = (12, 18)

# Spans the scenario-v1 ranges, including inocula far below and close to K.
PARAM_GRID = [
    (k, r, x0)
    for k in (0.4, 1.0, 1.8, 4.0, 10.0)
    for r in (0.6, 0.75, 0.9)
    for x0 in (0.005, 0.01, 0.02)
]
T_GRID = np.linspace(0.0, 18.0, 721)


def _loguniform(rng: np.random.Generator, lo: float, hi: float, size: int) -> np.ndarray:
    return np.exp(rng.uniform(np.log(lo), np.log(hi), size))


# ---- T-002: analytic sanity ------------------------------------------------------


@pytest.mark.parametrize(("k", "r", "x0"), PARAM_GRID)
def test_t002_nu1_matches_logistic(k: float, r: float, x0: float) -> None:
    x = richards(T_GRID, k_odeq=k, r_per_h=r, x0_odeq=x0, nu=1.0)
    logistic = k / (1.0 + (k / x0 - 1.0) * np.exp(-r * T_GRID))
    assert np.max(np.abs(x - logistic) / logistic) <= 1e-12


@pytest.mark.parametrize("nu", [1.0, NU])
@pytest.mark.parametrize(("k", "r", "x0"), PARAM_GRID)
def test_t002_satisfies_richards_ode(nu: float, k: float, r: float, x0: float) -> None:
    h = 1e-4
    t = T_GRID[1:-1]
    fd = (
        richards(t + h, k_odeq=k, r_per_h=r, x0_odeq=x0, nu=nu)
        - richards(t - h, k_odeq=k, r_per_h=r, x0_odeq=x0, nu=nu)
    ) / (2 * h)
    x = richards(t, k_odeq=k, r_per_h=r, x0_odeq=x0, nu=nu)
    ode = r * x * (1.0 - (x / k) ** nu)
    # Normalised by r*X (the exponential-phase slope) because dX/dt -> 0 at the
    # plateau, where a residual relative to dX/dt itself would be ill-defined.
    assert np.max(np.abs(fd - ode) / (r * x)) <= 1e-5


@pytest.mark.parametrize("nu", [1.0, NU])
@pytest.mark.parametrize(("k", "r", "x0"), PARAM_GRID)
def test_t002_initial_value_monotone_and_bounded(nu: float, k: float, r: float, x0: float) -> None:
    x = richards(T_GRID, k_odeq=k, r_per_h=r, x0_odeq=x0, nu=nu)
    assert abs(x[0] - x0) / x0 <= 1e-12
    assert np.all(x <= k)
    # In float64 X(t) reaches K exactly once (X0^-nu - K^-nu) e^{-nu r t} drops below
    # one ulp of K^-nu, so strict increase is checked on the unsaturated part only.
    unsaturated = x < k * (1.0 - 1e-9)
    assert unsaturated.sum() >= 10
    assert np.all(np.diff(x[unsaturated]) > 0)
    assert np.all(np.diff(x) >= 0)


def test_t002_exponential_early_phase() -> None:
    # DESIGN §5.2: the early phase is exponential with rate r for every nu. K is
    # set far above X so the (X/K)^nu braking term is below 1e-7 even at nu = 1.
    t = np.linspace(0.0, 1.0, 11)
    for nu in (1.0, NU):
        x = richards(t, k_odeq=1e6, r_per_h=0.75, x0_odeq=0.01, nu=nu)
        assert np.allclose(x, 0.01 * np.exp(0.75 * t), rtol=1e-6)


def test_t002_vectorised_shape() -> None:
    t = np.arange(19.0).reshape(1, 19)
    assert richards(t, k_odeq=1.0, r_per_h=0.75, x0_odeq=0.01, nu=NU).shape == (1, 19)
    assert richards(18.0, k_odeq=1.0, r_per_h=0.75, x0_odeq=0.01, nu=NU).shape == ()


@pytest.mark.parametrize("bad", ["k_odeq", "r_per_h", "x0_odeq", "nu"])
@pytest.mark.parametrize("value", [0.0, -1.0])
def test_richards_rejects_non_positive_parameters(bad: str, value: float) -> None:
    params = dict(k_odeq=1.0, r_per_h=0.75, x0_odeq=0.01, nu=NU)
    params[bad] = value
    with pytest.raises(ValueError, match=bad):
        richards(1.0, **params)


# ---- T-003: biological plateau reaches K -----------------------------------------


def test_t003_bp_plateau_reaches_k() -> None:
    rng = np.random.default_rng(3)
    m = 1000
    s = _loguniform(rng, *S_RANGE, m)
    kappa = rng.uniform(*KAPPA_RANGE, m)
    r = rng.uniform(*R_RANGE, m)
    x0 = _loguniform(rng, *X0_RANGE, m)
    # Slowest corner: lowest r, smallest X0, largest K.
    s = np.append(s, S_RANGE[1])
    kappa = np.append(kappa, KAPPA_RANGE[1])
    r = np.append(r, R_RANGE[0])
    x0 = np.append(x0, X0_RANGE[0])
    k = kappa * s

    t = np.unique(np.concatenate([np.linspace(0.0, 18.0, 181), LATE_WINDOW_H]).astype(float))
    for ki, ri, x0i in zip(k, r, x0, strict=True):
        x = richards(t, k_odeq=ki, r_per_h=ri, x0_odeq=x0i, nu=NU)
        assert np.all(x <= ki)
        assert x[t == 18.0][0] / ki >= 0.9999
        assert x[t == 12.0][0] <= ki
