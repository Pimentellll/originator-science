"""T-004 to T-007 and the noise model: assay response (DESIGN §5.3-5.6).

The DEV-002 scenario sampler does not exist yet. T-004 and T-005 therefore draw
configurations here from the scenario-v1 ranges in DESIGN §5.8, using a fixed-seed
Generator, and add the worst-case range corners explicitly. Latent biomass for T-005
uses the Richards closed form inline (DESIGN §5.2) so this branch does not depend on
DEV-003.
"""

from __future__ import annotations

import numpy as np
import pytest

from mirage.assay.od_reader import (
    compression,
    k_prime,
    noise_sd,
    read,
    response,
    t_q,
    x_lin,
)

# DESIGN §5.8 (scenario-v1)
N = 8.0
NU = 8.0
S_RANGE = (0.5, 2.0)  # log-uniform, ODeq
KAPPA_RANGE = (0.80, 0.90)  # BIOLOGICAL_PLATEAU
LAMBDA_RANGE = (3.0, 5.0)  # MEASUREMENT_ARTIFACT
R_RANGE = (0.6, 0.9)  # 1/h
X0_RANGE = (0.005, 0.02)  # log-uniform, ODeq
SIGMA_ABS = 0.003
SIGMA_REL = 0.02
EPS_LIN = 0.05
PLATEAU_FRACTION = 0.95
LATE_WINDOW_H = (12, 18)

S_VALUES = (0.5, 1.0, 2.0)


def _loguniform(rng: np.random.Generator, lo: float, hi: float, size: int) -> np.ndarray:
    return np.exp(rng.uniform(np.log(lo), np.log(hi), size))


def _sample(
    rng: np.random.Generator, ratio_range: tuple[float, float], m: int, *, corners: bool
) -> dict[str, np.ndarray]:
    """m configs from the §5.8 ranges, optionally plus all 16 corners of (S, ratio, r, X0)."""
    s = _loguniform(rng, *S_RANGE, m)
    ratio = rng.uniform(*ratio_range, m)
    r = rng.uniform(*R_RANGE, m)
    x0 = _loguniform(rng, *X0_RANGE, m)
    if corners:
        grid = np.array(np.meshgrid(S_RANGE, ratio_range, R_RANGE, X0_RANGE)).reshape(4, -1)
        s, ratio, r, x0 = (np.concatenate([a, c]) for a, c in zip((s, ratio, r, x0), grid, strict=True))
    return dict(s=s, k=ratio * s, r=r, x0=x0)


def _latent(t: float, k: float, r: float, x0: float) -> float:
    return (k**-NU + (x0**-NU - k**-NU) * np.exp(-NU * r * t)) ** (-1.0 / NU)


# ---- T-004: BP stays inside the intended measurement regime -----------------------


def test_t004_bp_inside_measurement_regime() -> None:
    cfg = _sample(np.random.default_rng(4), KAPPA_RANGE, 10_000, corners=True)
    comp, k_over_kp, below_xlin = [], [], []
    for s, k in zip(cfg["s"], cfg["k"], strict=True):
        comp.append(float(compression(k, s_odeq=s, n=N)))
        k_over_kp.append(k / k_prime(k_odeq=k, s_odeq=s, n=N))
        below_xlin.append(k <= x_lin(s_odeq=s, n=N, eps_lin=EPS_LIN))
    assert max(comp) <= 0.05
    assert all(below_xlin)
    assert max(k_over_kp) <= 1.053
    # Worst case kappa = 0.9: 1 - (1 + 0.9^8)^(-1/8); design-time maximum 0.0438.
    assert max(comp) == pytest.approx(0.0438, abs=1e-4)


# ---- T-005: MA latent biomass well above the apparent plateau ---------------------


def test_t005_ma_latent_far_above_apparent_plateau() -> None:
    cfg = _sample(np.random.default_rng(5), LAMBDA_RANGE, 10_000, corners=True)
    late_12, late_18 = [], []
    for s, k, r, x0 in zip(cfg["s"], cfg["k"], cfg["r"], cfg["x0"], strict=True):
        kp = k_prime(k_odeq=k, s_odeq=s, n=N)
        late_12.append(_latent(LATE_WINDOW_H[0], k, r, x0) / kp)
        late_18.append(_latent(LATE_WINDOW_H[1], k, r, x0) / kp)
    assert min(late_18) >= 2.95
    assert min(late_12) >= 2.5


@pytest.mark.parametrize("ratio_range", [KAPPA_RANGE, LAMBDA_RANGE], ids=["BP", "MA"])
def test_t005_t95_precedes_late_window(ratio_range: tuple[float, float]) -> None:
    # Sampled configs only, as T-005 specifies: see the corner test below.
    cfg = _sample(np.random.default_rng(55), ratio_range, 10_000, corners=False)
    t95 = [
        t_q(PLATEAU_FRACTION, k_odeq=k, s_odeq=s, r_per_h=r, x0_odeq=x0, n=N, nu=NU)
        for s, k, r, x0 in zip(cfg["s"], cfg["k"], cfg["r"], cfg["x0"], strict=True)
    ]
    assert max(t95) + 2.0 <= LATE_WINDOW_H[0]


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="open spec question (PR #3, G0-C(iv)): sup t95 over the scenario-v1 support is 10.13 h > 10 h",
)
def test_t005_window_validity_at_support_corner() -> None:
    # Slowest corner of the support (S = 2, lambda = 5, r = 0.6, X0 = 0.005). The
    # design-time 11.92 h is a sampled maximum, not the supremum. Strict xfail: this
    # fails loudly if t_q or the parameters change so that the corner passes.
    t95 = t_q(PLATEAU_FRACTION, k_odeq=10.0, s_odeq=2.0, r_per_h=0.6, x0_odeq=0.005, n=N, nu=NU)
    assert t95 + 2.0 <= LATE_WINDOW_H[0]


def test_t_q_matches_noise_free_observed_curve() -> None:
    # Demo-pair MA episode (DESIGN §7): K' = 1.000, t95 = 6.25 h.
    k, s, r, x0 = 4.0, 1.0, 0.75, 0.01
    t95 = t_q(PLATEAU_FRACTION, k_odeq=k, s_odeq=s, r_per_h=r, x0_odeq=x0, n=N, nu=NU)
    assert t95 == pytest.approx(6.25, abs=5e-3)
    kp = k_prime(k_odeq=k, s_odeq=s, n=N)
    assert kp == pytest.approx(1.000, abs=5e-4)
    y = float(response(_latent(t95, k, r, x0), s_odeq=s, n=N))
    assert y == pytest.approx(PLATEAU_FRACTION * kp, rel=1e-12)


def test_t_q_analytic_large_inoculum_non_default_shape() -> None:
    # Second parameter set: large X0, n = nu = 4, q = 0.9. With n = nu the observed curve
    # is Richards(K', f(X0), r, nu), so t_q has the closed form checked independently here.
    k, s, r, x0, n, q = 3.0, 1.0, 0.5, 0.3, 4.0, 0.9
    tq = t_q(q, k_odeq=k, s_odeq=s, r_per_h=r, x0_odeq=x0, n=n, nu=n)
    kp = (k**-n + s**-n) ** (-1.0 / n)
    y0 = x0 * (1.0 + (x0 / s) ** n) ** (-1.0 / n)
    expected = np.log((y0**-n - kp**-n) / ((q * kp) ** -n - kp**-n)) / (n * r)
    assert tq == pytest.approx(expected, rel=1e-12)
    latent = (k**-n + (x0**-n - k**-n) * np.exp(-n * r * tq)) ** (-1.0 / n)
    assert float(response(latent, s_odeq=s, n=n)) == pytest.approx(q * kp, rel=1e-12)


# ---- T-006: low-density response approximately linear ----------------------------


@pytest.mark.parametrize("s", S_VALUES)
def test_t006_low_density_linear(s: float) -> None:
    x = s * np.geomspace(1e-4, 0.733, 2000)
    c = compression(x, s_odeq=s, n=N)
    assert np.all(c[x <= 0.5 * s] <= 0.001)
    assert np.all(c[x <= 0.733 * s] <= 0.01)
    # DESIGN §5.3 table: compression <= 0.05 % at 0.5 S, <= 1 % at 0.733 S.
    assert float(compression(0.5 * s, s_odeq=s, n=N)) <= 0.0005
    x_small = 1e-3 * s
    assert abs(float(response(x_small, s_odeq=s, n=N)) / x_small - 1.0) <= 1e-9
    assert np.allclose(c, 1.0 - response(x, s_odeq=s, n=N) / x, rtol=0, atol=1e-15)


# ---- T-007: high-density response becomes sublinear ------------------------------


@pytest.mark.parametrize("s", S_VALUES)
def test_t007_high_density_sublinear(s: float) -> None:
    x = s * np.linspace(0.5, 10.0, 2000)
    y = response(x, s_odeq=s, n=N)
    assert np.all(np.diff(y) > 0)
    assert np.all(y < s)
    assert np.all(np.diff(y / x) < 0)
    assert 0.49 <= float(compression(2 * s, s_odeq=s, n=N)) <= 0.51
    h = 1e-4 * s
    slope = (float(response(3 * s + h, s_odeq=s, n=N)) - float(response(3 * s - h, s_odeq=s, n=N))) / (2 * h)
    assert 0 < slope < 1e-3
    assert x_lin(s_odeq=s, n=N, eps_lin=EPS_LIN) / s == pytest.approx(0.9187, abs=1e-4)
    assert float(compression(x_lin(s_odeq=s, n=N, eps_lin=EPS_LIN), s_odeq=s, n=N)) == pytest.approx(EPS_LIN, rel=1e-12)


@pytest.mark.parametrize("s", S_VALUES)
def test_ceiling_values(s: float) -> None:
    # DESIGN §5.3: f(2S) = 0.9995 S, f(3S) = 0.99998 S, f -> S.
    assert float(response(2 * s, s_odeq=s, n=N)) / s == pytest.approx(0.9995, abs=5e-5)
    assert float(response(3 * s, s_odeq=s, n=N)) / s == pytest.approx(0.99998, abs=5e-6)
    assert float(response(0.0, s_odeq=s, n=N)) == 0.0


def test_k_prime_identity() -> None:
    # f(K) == K' : the apparent plateau is the response at the carrying capacity.
    for s in S_VALUES:
        for k in (0.8 * s, 0.9 * s, 3 * s, 5 * s):
            assert k_prime(k_odeq=k, s_odeq=s, n=N) == pytest.approx(float(response(k, s_odeq=s, n=N)), rel=1e-14)


# ---- Noise model (DESIGN §5.6) ---------------------------------------------------


def test_read_is_deterministic_given_generator() -> None:
    x = np.linspace(0.0, 3.0, 19)
    kw = dict(s_odeq=1.0, n=N, sigma_abs=SIGMA_ABS, sigma_rel=SIGMA_REL)
    a = read(x, np.random.default_rng(123), **kw)
    b = read(x, np.random.default_rng(123), **kw)
    c = read(x, np.random.default_rng(124), **kw)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_read_formula_and_rounding() -> None:
    x = np.linspace(0.0, 3.0, 19)
    s = 1.3
    y = read(x, np.random.default_rng(7), s_odeq=s, n=N, sigma_abs=SIGMA_ABS, sigma_rel=SIGMA_REL)
    mu = response(x, s_odeq=s, n=N)
    z = np.random.default_rng(7).standard_normal(19)
    assert np.array_equal(y, np.round(mu + (SIGMA_ABS + SIGMA_REL * mu) * z, 4))
    assert np.allclose(y * 1e4, np.round(y * 1e4), rtol=0, atol=1e-6)


def test_read_noise_statistics_and_no_clipping() -> None:
    m = 200_000
    for mu_x in (0.0, 0.5):
        x = np.full(m, mu_x)
        y = read(x, np.random.default_rng(11), s_odeq=1.0, n=N, sigma_abs=SIGMA_ABS, sigma_rel=SIGMA_REL)
        mu = float(response(mu_x, s_odeq=1.0, n=N))
        sd = SIGMA_ABS + SIGMA_REL * mu
        assert abs(y.mean() - mu) <= 5 * sd / np.sqrt(m)
        assert y.std() == pytest.approx(sd, rel=0.01)
    # Blank readings are not clipped at zero.
    assert (y := read(np.zeros(1000), np.random.default_rng(1), s_odeq=1.0, n=N,
                      sigma_abs=SIGMA_ABS, sigma_rel=SIGMA_REL)).min() < 0


def test_noise_sd() -> None:
    assert np.allclose(noise_sd([0.0, 1.0], sigma_abs=SIGMA_ABS, sigma_rel=SIGMA_REL), [0.003, 0.023])


# ---- Validation -------------------------------------------------------------------


def test_rejects_negative_biomass_and_bad_parameters() -> None:
    with pytest.raises(ValueError):
        response(-1e-9, s_odeq=1.0, n=N)
    with pytest.raises(ValueError):
        read([0.1, -0.1], np.random.default_rng(0), s_odeq=1.0, n=N, sigma_abs=SIGMA_ABS, sigma_rel=SIGMA_REL)
    with pytest.raises(ValueError):
        response(0.1, s_odeq=0.0, n=N)
    with pytest.raises(ValueError):
        k_prime(k_odeq=-1.0, s_odeq=1.0, n=N)
    with pytest.raises(ValueError):
        x_lin(s_odeq=1.0, n=N, eps_lin=1.0)
    with pytest.raises(ValueError):
        t_q(1.0, k_odeq=1.0, s_odeq=1.0, r_per_h=0.75, x0_odeq=0.01, n=N, nu=NU)


@pytest.mark.parametrize("value", [float("inf"), float("nan")])
def test_rejects_non_finite_saturation_scale(value: float) -> None:
    with pytest.raises(ValueError, match="s_odeq"):
        response(0.1, s_odeq=value, n=N)
    with pytest.raises(ValueError, match="s_odeq"):
        k_prime(k_odeq=1.0, s_odeq=value, n=N)


@pytest.mark.parametrize("name", ["sigma_abs", "sigma_rel"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.001])
def test_rejects_non_finite_or_negative_noise(name: str, value: float) -> None:
    params = dict(sigma_abs=SIGMA_ABS, sigma_rel=SIGMA_REL)
    params[name] = value
    with pytest.raises(ValueError, match=name):
        read([0.1], np.random.default_rng(0), s_odeq=1.0, n=N, **params)
