"""OD600-like assay model: saturating response, useful region, apparent plateau, noise.

Implements DESIGN §5.3-5.6. Hidden module: it never sees the condition or K's origin;
``k_prime`` and ``t_q`` take K only as a number for Gate 0 diagnostics.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike, NDArray

# DESIGN §5.6: readings are reported rounded to 4 decimal places (resolution 0.0001).
READING_DECIMALS = 4


def _require_positive(**params: float) -> None:
    for name, value in params.items():
        if not (math.isfinite(value) and value > 0):
            raise ValueError(f"{name} must be finite and positive, got {value!r}")


def _biomass(x_odeq: ArrayLike) -> NDArray[np.float64]:
    x = np.asarray(x_odeq, dtype=np.float64)
    if np.any(x < 0) or np.any(np.isnan(x)):
        raise ValueError("presented biomass must be non-negative")
    return x


def response(x_odeq: ArrayLike, *, s_odeq: float, n: float) -> NDArray[np.float64]:
    """Noise-free reading f(x) = x [1 + (x/S)^n]^(-1/n) in ODeq for presented biomass x (ODeq).

    Written as x * (...) rather than (x^-n + S^-n)^(-1/n) so that f(0) = 0 without
    a division by zero. (x/S)^n overflows for x around 1e40 and returns 0.0; presented
    biomass in scenario-v1 is at most about 10 ODeq, so this is unreachable.
    """
    _require_positive(s_odeq=s_odeq, n=n)
    x = _biomass(x_odeq)
    return x * (1.0 + (x / s_odeq) ** n) ** (-1.0 / n)


def compression(x_odeq: ArrayLike, *, s_odeq: float, n: float) -> NDArray[np.float64]:
    """Fractional compression c(x) = 1 - f(x)/x = 1 - [1 + (x/S)^n]^(-1/n) (dimensionless).

    Evaluated directly from the closed form so that it is defined (= 0) at x = 0.
    """
    _require_positive(s_odeq=s_odeq, n=n)
    x = _biomass(x_odeq)
    return 1.0 - (1.0 + (x / s_odeq) ** n) ** (-1.0 / n)


def x_lin(*, s_odeq: float, n: float, eps_lin: float) -> float:
    """Upper edge of the useful region in ODeq: x_lin = S [(1 - eps)^-n - 1]^(1/n)."""
    _require_positive(s_odeq=s_odeq, n=n, eps_lin=eps_lin)
    if not eps_lin < 1:
        raise ValueError(f"eps_lin must be < 1, got {eps_lin!r}")
    return s_odeq * ((1.0 - eps_lin) ** -n - 1.0) ** (1.0 / n)


def k_prime(*, k_odeq: float, s_odeq: float, n: float) -> float:
    """Apparent (observed) plateau K' = (K^-n + S^-n)^(-1/n) in ODeq (DESIGN §5.4)."""
    _require_positive(k_odeq=k_odeq, s_odeq=s_odeq, n=n)
    return (k_odeq**-n + s_odeq**-n) ** (-1.0 / n)


def t_q(
    q: float,
    *,
    k_odeq: float,
    s_odeq: float,
    r_per_h: float,
    x0_odeq: float,
    n: float,
    nu: float,
) -> float:
    """Time in hours at which the noise-free observed curve reaches q * K' (DESIGN §5.5).

    t_q = ln[(y0^-nu - K'^-nu) / ((q K')^-nu - K'^-nu)] / (nu r), with y0 = f(X0).
    Exact only when n == nu (the observed curve is then itself Richards).
    """
    _require_positive(k_odeq=k_odeq, s_odeq=s_odeq, r_per_h=r_per_h, x0_odeq=x0_odeq, n=n, nu=nu)
    if not 0 < q < 1:
        raise ValueError(f"q must be in (0, 1), got {q!r}")
    kp = k_prime(k_odeq=k_odeq, s_odeq=s_odeq, n=n)
    y0 = float(response(x0_odeq, s_odeq=s_odeq, n=n))
    return math.log((y0**-nu - kp**-nu) / ((q * kp) ** -nu - kp**-nu)) / (nu * r_per_h)


def noise_sd(mu: ArrayLike, *, sigma_abs: float, sigma_rel: float) -> NDArray[np.float64]:
    """Per-replicate noise SD sigma(mu) = sigma_abs + sigma_rel * mu in ODeq (DESIGN §5.6)."""
    for name, value in (("sigma_abs", sigma_abs), ("sigma_rel", sigma_rel)):
        if not (math.isfinite(value) and value >= 0):
            raise ValueError(f"{name} must be finite and non-negative, got {value!r}")
    return sigma_abs + sigma_rel * np.asarray(mu, dtype=np.float64)


def read(
    x_odeq: ArrayLike,
    rng: np.random.Generator,
    *,
    s_odeq: float,
    n: float,
    sigma_abs: float,
    sigma_rel: float,
) -> NDArray[np.float64]:
    """Noisy readings in ODeq, one per element of presented biomass ``x_odeq`` (ODeq).

    y = round_4(f(x) + sigma(f(x)) z), z ~ N(0, 1) drawn from ``rng`` in element order.
    Readings are not clipped: blank-subtracted readings may be slightly negative.
    """
    mu = response(x_odeq, s_odeq=s_odeq, n=n)
    z = rng.standard_normal(mu.shape)
    return np.round(mu + noise_sd(mu, sigma_abs=sigma_abs, sigma_rel=sigma_rel) * z, READING_DECIMALS)
