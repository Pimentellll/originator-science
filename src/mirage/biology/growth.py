"""Closed-form Richards (generalised logistic) growth of latent biomass (DESIGN §5.2).

Hidden module: it knows nothing about the assay, the condition or the agent.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike, NDArray


def richards(
    t_h: ArrayLike,
    *,
    k_odeq: float,
    r_per_h: float,
    x0_odeq: float,
    nu: float,
) -> NDArray[np.float64]:
    """Latent biomass X(t) in ODeq at times ``t_h`` (hours).

    Solves dX/dt = r X [1 - (X/K)^nu], X(0) = X0, via the inverse-power closed form
    X^-nu = K^-nu + (X0^-nu - K^-nu) exp(-nu r t). Vectorised over ``t_h``; always
    returns an ndarray with the shape of ``t_h`` (0-d for a scalar time).
    Raises ``ValueError`` unless every parameter is finite and positive and X0 <= K.
    """
    for name, value in (("k_odeq", k_odeq), ("r_per_h", r_per_h), ("x0_odeq", x0_odeq), ("nu", nu)):
        if not (math.isfinite(value) and value > 0):
            raise ValueError(f"{name} must be finite and positive, got {value!r}")
    # X0 > K would make X^-nu cross zero at finite t (blow-up to inf), which is not growth.
    if x0_odeq > k_odeq:
        raise ValueError(f"x0_odeq must not exceed k_odeq, got x0_odeq={x0_odeq!r} > k_odeq={k_odeq!r}")
    t = np.asarray(t_h, dtype=np.float64)
    # Inverse-power form avoids the overflow of (K/X0)^nu when X0 << K and nu = 8.
    inv = k_odeq**-nu + (x0_odeq**-nu - k_odeq**-nu) * np.exp(-nu * r_per_h * t)
    return np.asarray(inv ** (-1.0 / nu), dtype=np.float64)
