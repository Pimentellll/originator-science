"""Proposed scorer changes P1-P4 (REGISTRATION.md), recomputed from episode records only.

Read-only: nothing here writes to a record or changes the frozen evaluator.
"""

from __future__ import annotations

import math
from functools import cache

import numpy as np

from mirage.agents.scripted import PLATEAU_TIMES_H
from mirage.assay.od_reader import response
from mirage.biology.growth import richards
from mirage.config import ScenarioPrior
from mirage.evaluation.metrics import EpisodeResult

ABOVE, AS_READ = "BIOMASS_ABOVE_READING", "BIOMASS_AS_READ"
GRID_POINTS = 201
P3_TOLERANCES = (0.05, 0.10, 0.25)
P3_PRIMARY = 0.10


def noise_free_ratio(c: np.ndarray | float, d: float, n: float) -> np.ndarray:
    """R(c, d) = d f(c/d) / f(c) with S = 1 (f is scale-invariant in S)."""
    c = np.asarray(c, dtype=np.float64)
    return d * response(c / d, s_odeq=1.0, n=n) / response(c, s_odeq=1.0, n=n)


@cache
def _tau(
    d: float, n: float, kappa: tuple[float, float], lam: tuple[float, float]
) -> float:
    r_bp = noise_free_ratio(np.linspace(*kappa, GRID_POINTS), d, n).max()
    r_ma = noise_free_ratio(np.linspace(*lam, GRID_POINTS), d, n).min()
    return float(math.sqrt(r_bp * r_ma))


def tau(d: float, prior: ScenarioPrior) -> float:
    """Per-d evidence threshold: geometric midpoint of the noise-free BP max and MA min."""
    return _tau(
        float(d),
        float(prior.n),
        tuple(prior.kappa_uniform),
        tuple(prior.lambda_uniform),
    )


def plateau_mean(r: EpisodeResult) -> float:
    by_t = {m.time_h: m.mean_reading for m in r.passive}
    return sum(by_t[t] for t in PLATEAU_TIMES_H) / len(PLATEAU_TIMES_H)


def control_evidence(r: EpisodeResult, prior: ScenarioPrior) -> list[dict]:
    """(t, d, R, tau, label) for every diagnostic-control measurement, from what the agent saw."""
    events = {e.index: e for e in r.events}
    p_hat = plateau_mean(r)
    out = []
    for m in r.audit:
        if not m.diagnostic_control:
            continue
        res = events[m.event_index].result
        d = float(res["dilution_factor"])
        ratio = d * float(np.mean(res["readings"])) / p_hat
        t = tau(d, prior)
        out.append(
            {
                "time_h": res["time_h"],
                "dilution_factor": d,
                "R": ratio,
                "tau": t,
                "label": ABOVE if ratio >= t else AS_READ,
            }
        )
    return out


def evidence_label(evidence: list[dict]) -> str | None:
    """Majority label over diagnostic controls; None for no control; 'TIE' for a tie."""
    if not evidence:
        return None
    above = sum(e["label"] == ABOVE for e in evidence)
    below = len(evidence) - above
    return ABOVE if above > below else AS_READ if below > above else "TIE"


def justified_p1(r: EpisodeResult, prior: ScenarioPrior) -> bool:
    if not r.scores.justified:
        return False
    ev = evidence_label(control_evidence(r, prior))
    return ev == "TIE" or ev == r.diagnosis.diagnosis


def justified_p4(r: EpisodeResult) -> bool:
    if not r.scores.justified:
        return False
    p = r.diagnosis.p_biomass_above_reading
    return p > 0.5 if r.diagnosis.diagnosis == ABOVE else p < 0.5


def justified_p2(r: EpisodeResult, twin_label: str | None) -> bool | None:
    """Justified and the label flips when every measurement comes from the matched twin."""
    if twin_label is None:
        return None
    return bool(r.scores.justified and twin_label != r.diagnosis.diagnosis)


def latent_18(r: EpisodeResult) -> float:
    return float(richards(18, **r.episode.growth.model_dump()))


def estimate_rel_error(r: EpisodeResult) -> float | None:
    if r.diagnosis is None or r.diagnosis.late_biomass_estimate_od is None:
        return None
    return r.diagnosis.late_biomass_estimate_od / latent_18(r) - 1.0


def q1_p3(r: EpisodeResult, tol: float = P3_PRIMARY) -> bool:
    err = estimate_rel_error(r)
    return r.scores.reconstruction_adequate and err is not None and abs(err) <= tol


def compact(r: EpisodeResult, prior: ScenarioPrior, twin_label: str | None) -> dict:
    """One JSON-able row per episode: frozen scores plus every proposed-rule input and output."""
    ev = control_evidence(r, prior)
    d = r.diagnosis
    row = {
        "episode_id": r.episode.episode_id,
        "seed": r.episode.seed,
        "condition": r.episode.condition.value,
        "status": r.status,
        "diagnosis": d.diagnosis if d else None,
        "p": d.p_biomass_above_reading if d else None,
        "estimate": d.late_biomass_estimate_od if d else None,
        "latent_18": latent_18(r),
        "measurements": [
            {k: e.arguments[k] for k in ("time_h", "dilution_factor", "replicates")}
            for e in r.events
            if e.tool == "measure_od" and e.ok
        ],
        "scores": r.scores.model_dump(mode="json"),
        "evidence": ev,
        "evidence_label": evidence_label(ev),
        "estimate_rel_error": estimate_rel_error(r),
        "justified_p1": justified_p1(r, prior),
        "justified_p4": justified_p4(r),
        **{f"q1_p3_{tol:.2f}": q1_p3(r, tol) for tol in P3_TOLERANCES},
        "twin_label": twin_label,
        "justified_p2": justified_p2(r, twin_label),
    }
    return row
