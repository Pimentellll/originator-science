"""HIDDEN: the two hidden conditions and how each sets the carrying capacity K (DESIGN §6)."""

from __future__ import annotations

from enum import Enum


class Condition(str, Enum):
    BIOLOGICAL_PLATEAU = "BIOLOGICAL_PLATEAU"
    MEASUREMENT_ARTIFACT = "MEASUREMENT_ARTIFACT"


ABBREVIATION = {
    Condition.BIOLOGICAL_PLATEAU: "BP",
    Condition.MEASUREMENT_ARTIFACT: "MA",
}


def k_from_condition(
    condition: Condition | str,
    *,
    s_odeq: float,
    u: float,
    kappa_uniform: tuple[float, float],
    lambda_uniform: tuple[float, float],
) -> tuple[float, float]:
    """Return ``(K, ratio)`` in ODeq, with ratio = kappa or lambda at quantile ``u``.

    K = ratio * S. ``u`` is the uniform draw u_K. Raises ``ValueError`` on an unknown
    condition.
    """
    condition = Condition(condition)
    if condition is Condition.BIOLOGICAL_PLATEAU:
        lo, hi = kappa_uniform
    else:
        lo, hi = lambda_uniform
    ratio = lo + u * (hi - lo)
    return ratio * s_odeq, ratio
