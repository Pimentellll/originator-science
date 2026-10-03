"""HIDDEN: scenario schemas, prior loading, episode sampling and canonical hashing.

DESIGN §6 (sampling order), §13 (schemas), §18 (RNG streams).
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mirage.biology.conditions import ABBREVIATION, Condition, k_from_condition

SCENARIO_STREAM = 0


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GrowthConfig(Frozen):
    r_per_h: float = Field(gt=0)
    x0_odeq: float = Field(gt=0)
    k_odeq: float = Field(gt=0)
    nu: float = Field(gt=0)


class AssayConfig(Frozen):
    s_odeq: float = Field(gt=0)
    n: float = Field(gt=0)
    sigma_abs: float = Field(ge=0)
    sigma_rel: float = Field(ge=0)
    resolution: float = Field(gt=0)
    eps_lin: float = Field(gt=0, lt=1)
    y_loq: float = Field(gt=0)


class ScenarioPrior(Frozen):
    scenario_version: Literal["scenario-v1"]
    s_odeq_loguniform: tuple[float, float]
    r_per_h_uniform: tuple[float, float]
    x0_odeq_loguniform: tuple[float, float]
    kappa_uniform: tuple[float, float]
    lambda_uniform: tuple[float, float]
    # Bounds mirror GrowthConfig / AssayConfig, which every sampled episode must satisfy.
    nu: float = Field(gt=0, allow_inf_nan=False)
    n: float = Field(gt=0, allow_inf_nan=False)
    sigma_abs: float = Field(ge=0, allow_inf_nan=False)
    sigma_rel: float = Field(ge=0, allow_inf_nan=False)
    resolution: float = Field(gt=0, allow_inf_nan=False)
    eps_lin: float = Field(gt=0, lt=1, allow_inf_nan=False)
    y_loq: float = Field(gt=0, allow_inf_nan=False)
    passive_times_h: list[int] = Field(min_length=1)
    max_time_h: int
    dilution_range: tuple[float, float]
    max_replicates: int
    budget_units: int
    max_turns: int
    plateau_fraction: float = Field(allow_inf_nan=False)
    late_window_h: tuple[int, int]

    @model_validator(mode="after")
    def _check_ranges(self) -> ScenarioPrior:
        for name in (
            "s_odeq_loguniform",
            "r_per_h_uniform",
            "x0_odeq_loguniform",
            "kappa_uniform",
            "lambda_uniform",
            "dilution_range",
            "late_window_h",
        ):
            lo, hi = getattr(self, name)
            if not (math.isfinite(lo) and math.isfinite(hi) and lo < hi):
                raise ValueError(f"{name} must be a finite (lo, hi) with lo < hi")
        for name in ("s_odeq_loguniform", "x0_odeq_loguniform"):
            if getattr(self, name)[0] <= 0:
                raise ValueError(f"{name} is log-uniform and needs lo > 0")
        return self


class EpisodeConfig(Frozen):
    episode_id: str
    seed: int
    condition: Condition
    scenario_version: str
    scenario_sha256: str
    k_ratio: float
    growth: GrowthConfig
    assay: AssayConfig


def canonical_sha256(prior: ScenarioPrior) -> str:
    """SHA-256 of the validated prior as compact, key-sorted JSON (formatting-independent)."""
    text = json.dumps(
        prior.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_prior(path: str | Path) -> ScenarioPrior:
    """Load and validate ``scenario_v1.json``. Raises on invalid JSON or schema violation."""
    with open(path, encoding="utf-8") as fh:
        # NaN/Infinity tokens parse to floats here; the schema then rejects them as non-finite.
        data: Any = json.load(fh, parse_constant=float)
    prior = ScenarioPrior.model_validate(data)
    _check_visible_limits(prior)
    return prior


def _check_visible_limits(prior: ScenarioPrior) -> None:
    """The scenario's limits must equal the frozen visible constants the agent is told."""
    from mirage.lab import tools

    pairs = {
        "max_time_h": (prior.max_time_h, tools.MAX_TIME_H),
        "dilution_range": (prior.dilution_range[1], tools.MAX_DILUTION),
        "max_replicates": (prior.max_replicates, tools.MAX_REPLICATES),
        "budget_units": (prior.budget_units, tools.BUDGET_UNITS),
        "max_turns": (prior.max_turns, tools.MAX_TURNS),
    }
    for name, (got, want) in pairs.items():
        if got != want:
            raise ValueError(f"{name} {got!r} does not match mirage.lab.tools ({want!r})")


def _loguniform(u: float, lo: float, hi: float) -> float:
    return math.exp(math.log(lo) + u * (math.log(hi) - math.log(lo)))


def sample_episode(
    prior: ScenarioPrior, seed: int, condition: Condition | str
) -> EpisodeConfig:
    """Sample the hidden ``EpisodeConfig`` for ``(seed, condition)`` (DESIGN §6).

    Uses stream ``SeedSequence([seed, 0])``. u_S, u_r, u_X0, u_K are drawn before the
    condition is read, so S, r and X0 and the quantile of K are shared across conditions.
    """
    rng = np.random.default_rng(np.random.SeedSequence([seed, SCENARIO_STREAM]))
    u_s, u_r, u_x0, u_k = (float(u) for u in rng.random(4))
    s_odeq = _loguniform(u_s, *prior.s_odeq_loguniform)
    lo, hi = prior.r_per_h_uniform
    r_per_h = lo + u_r * (hi - lo)
    x0_odeq = _loguniform(u_x0, *prior.x0_odeq_loguniform)
    k_odeq, ratio = k_from_condition(
        condition,
        s_odeq=s_odeq,
        u=u_k,
        kappa_uniform=prior.kappa_uniform,
        lambda_uniform=prior.lambda_uniform,
    )
    condition = Condition(condition)
    return EpisodeConfig(
        episode_id=f"s{seed}-{ABBREVIATION[condition]}",
        seed=seed,
        condition=condition,
        scenario_version=prior.scenario_version,
        scenario_sha256=canonical_sha256(prior),
        k_ratio=ratio,
        growth=GrowthConfig(r_per_h=r_per_h, x0_odeq=x0_odeq, k_odeq=k_odeq, nu=prior.nu),
        assay=assay_config(prior, s_odeq),
    )


def assay_config(prior: ScenarioPrior, s_odeq: float) -> AssayConfig:
    """The episode's ``AssayConfig``: only S varies, everything else comes from the prior."""
    return AssayConfig(
        s_odeq=s_odeq,
        n=prior.n,
        sigma_abs=prior.sigma_abs,
        sigma_rel=prior.sigma_rel,
        resolution=prior.resolution,
        eps_lin=prior.eps_lin,
        y_loq=prior.y_loq,
    )


def load_demo_pair(
    path: str | Path, prior: ScenarioPrior, *, seeds: tuple[int, int]
) -> list[EpisodeConfig]:
    """Build the matched demo episodes from ``demo_pair.json`` (DESIGN §7, §20).

    The file fixes the hidden parameters; the caller supplies the noise seeds.
    """
    with open(path, encoding="utf-8") as fh:
        data: Any = json.load(fh)
    if data.get("scenario_version") != prior.scenario_version:
        raise ValueError("demo_pair.json scenario_version does not match the prior")
    sha = canonical_sha256(prior)
    episodes = []
    for entry, seed in zip(data["episodes"], seeds, strict=True):
        condition = Condition(entry["condition"])
        s_odeq = float(entry["s_odeq"])
        ratio = float(entry["k_ratio"])
        episodes.append(
            EpisodeConfig(
                episode_id=entry["episode_id"],
                seed=seed,
                condition=condition,
                scenario_version=prior.scenario_version,
                scenario_sha256=sha,
                k_ratio=ratio,
                growth=GrowthConfig(
                    r_per_h=float(entry["r_per_h"]),
                    x0_odeq=float(entry["x0_odeq"]),
                    k_odeq=ratio * s_odeq,
                    nu=prior.nu,
                ),
                assay=assay_config(prior, s_odeq),
            )
        )
    return episodes
