"""HIDDEN: episode record schemas (DESIGN §13 RECORDS).

Audit, scoring and aggregates (DESIGN §15). Must not import ``anthropic`` (§12).
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from mirage.assay.od_reader import response, x_lin
from mirage.biology.conditions import Condition
from mirage.biology.growth import richards
from mirage.config import EpisodeConfig, Frozen
from mirage.lab.tools import Diagnosis, MeasurementRequest, MeasurementResult

SCHEMA_VERSION = "episode-result-v1"

EpisodeStatus = Literal["DIAGNOSED", "NO_DIAGNOSIS", "API_FAILURE", "REFUSED"]


class EventRecord(Frozen):
    index: int = Field(ge=0)
    turn: int = Field(ge=1)
    tool: str
    arguments: dict[str, Any]
    ok: bool
    result: dict[str, Any] | None
    error: str | None


class MeasurementAudit(Frozen):
    event_index: int
    request_index: int
    latent_biomass_odeq: float = Field(ge=0, allow_inf_nan=False)
    presented_biomass_odeq: float = Field(ge=0, allow_inf_nan=False)
    noise_free_reading: float = Field(ge=0, allow_inf_nan=False)
    is_late: bool
    is_diluted: bool
    in_diagnostic_set: bool
    before_diagnosis: bool
    diagnostic_control: bool
    in_useful_region: bool
    reconstruction_adequate: bool

    @model_validator(mode="after")
    def _derived_clauses(self) -> MeasurementAudit:
        base = self.before_diagnosis and self.is_late and self.is_diluted
        if self.diagnostic_control != (base and self.in_diagnostic_set):
            raise ValueError("diagnostic_control contradicts its clauses")
        if self.reconstruction_adequate != (base and self.in_useful_region):
            raise ValueError("reconstruction_adequate contradicts its clauses")
        return self


class EpisodeScores(Frozen):
    correct: bool
    diagnostic_control: bool
    justified: bool
    reconstruction_adequate: bool
    cost_units: int = Field(ge=0)
    measure_calls_before_diagnosis: int = Field(ge=0)
    brier: float | None = Field(ge=0, le=1, allow_inf_nan=False)
    m5_diagnosticity: float | None = Field(ge=0, le=1, allow_inf_nan=False)


class AgentInfo(Frozen):
    name: str
    kind: Literal["llm", "scripted"]
    model: str | None
    effort: str | None
    prompt_version: str | None
    prompt_sha256: str | None
    sdk_version: str | None


class DiagnosticActionSet(Frozen):
    scenario_sha256: str
    late_window_h: tuple[int, int]
    d_min: float
    d_max: float
    auroc_threshold: float
    evaluated_replicates: int


class EpisodeResult(Frozen):
    schema_version: Literal["episode-result-v1"]
    episode: EpisodeConfig
    agent: AgentInfo
    passive: list[MeasurementResult]
    events: list[EventRecord]
    diagnosis: Diagnosis | None
    status: EpisodeStatus
    audit: list[MeasurementAudit]
    scores: EpisodeScores
    llm_transcript: list[dict[str, Any]] | None
    versions: dict[str, str]
    run_meta: dict[str, Any]

    @model_validator(mode="after")
    def _consistent(self) -> EpisodeResult:
        _check_record(self)
        return self


def _check_record(r: EpisodeResult) -> None:
    """Reject records whose events, diagnosis, status, audit and scores disagree."""
    ev = r.events
    if [e.index for e in ev] != list(range(len(ev))):
        raise ValueError("event indices must be 0..n-1 in order")
    if any(b.turn <= a.turn for a, b in zip(ev, ev[1:])):
        raise ValueError("event turns must strictly increase")
    diag_events = [e for e in ev if e.tool == "submit_diagnosis" and e.ok]
    if len(diag_events) > 1:
        raise ValueError("more than one accepted submit_diagnosis event")
    if diag_events and diag_events[0].index != ev[-1].index:
        raise ValueError("events recorded after the accepted diagnosis")
    if (r.status == "DIAGNOSED") != (r.diagnosis is not None) or (
        (r.diagnosis is None) != (not diag_events)
    ):
        raise ValueError("status, diagnosis and accepted submit_diagnosis event disagree")
    if r.diagnosis is not None and Diagnosis(**diag_events[0].arguments) != r.diagnosis:
        raise ValueError("diagnosis differs from the accepted submit_diagnosis arguments")
    accepted = [e for e in ev if e.tool == "measure_od" and e.ok]
    if [m.event_index for m in r.audit] != [e.index for e in accepted]:
        raise ValueError("audit must cover exactly the accepted measure_od events")
    if [m.request_index for m in r.audit] != list(range(len(r.audit))):
        raise ValueError("audit request indices must be 0..n-1")
    e_d = _diagnosis_event_index(ev)
    if any(m.before_diagnosis != (m.event_index < e_d) for m in r.audit):
        raise ValueError("audit before_diagnosis disagrees with the event order")
    for m, e in zip(r.audit, accepted):
        d = MeasurementRequest(**e.arguments).dilution_factor
        if m.is_diluted != (d > 1):
            raise ValueError("audit is_diluted disagrees with the event's dilution_factor")
        if not math.isclose(m.presented_biomass_odeq, m.latent_biomass_odeq / d, rel_tol=1e-9):
            raise ValueError("audit presented_biomass_odeq != latent_biomass_odeq / dilution")
    sc = r.scores
    correct = r.diagnosis is not None and (
        LABEL_TO_CONDITION[r.diagnosis.diagnosis] is r.episode.condition
    )
    control = any(m.diagnostic_control for m in r.audit)
    truth = 1.0 if r.episode.condition is Condition.MEASUREMENT_ARTIFACT else 0.0
    brier = None if r.diagnosis is None else (r.diagnosis.p_growth_continued - truth) ** 2
    expected = {
        "correct": correct,
        "diagnostic_control": control,
        "justified": correct and control,
        "reconstruction_adequate": any(m.reconstruction_adequate for m in r.audit),
        "cost_units": sum(MeasurementRequest(**e.arguments).replicates for e in accepted),
        "measure_calls_before_diagnosis": sum(
            1 for e in ev if e.tool == "measure_od" and e.index < e_d
        ),
    }
    for name, want in expected.items():
        if getattr(sc, name) != want:
            raise ValueError(f"scores.{name} disagrees with the record")
    if (sc.brier is None) != (brier is None) or (
        brier is not None
        and sc.brier is not None
        and not math.isclose(sc.brier, brier, abs_tol=1e-12)
    ):
        raise ValueError("scores.brier disagrees with the diagnosis")


# ---- audit and scoring (DESIGN §15) ------------------------------------------

LABEL_TO_CONDITION = {
    "GROWTH_STOPPED": Condition.BIOLOGICAL_PLATEAU,
    "GROWTH_CONTINUED": Condition.MEASUREMENT_ARTIFACT,
}
PRIMARY_STATUSES = ("DIAGNOSED", "NO_DIAGNOSIS")
WILSON_Z = 1.959963984540054


def is_late(time_h: float, late_window_h: tuple[int, int]) -> bool:
    """Visible late-window clause: depends only on the requested clock time (T-027)."""
    lo, hi = late_window_h
    return lo <= time_h <= hi


def load_diagnostic_action_set(
    summary_path: str | Path, scenario_sha256: str
) -> DiagnosticActionSet:
    """Read the frozen D_diag from a Gate 0 ``summary.json``.

    Raises ``ValueError`` if the set is missing or incomplete, or if its scenario hash does
    not match ``scenario_sha256`` (T-032).
    """
    with open(summary_path, encoding="utf-8") as fh:
        summary: Any = json.load(fh)
    raw = summary.get("diagnostic_action_set")
    if not raw or raw.get("d_min") is None or raw.get("d_max") is None:
        raise ValueError("summary.json has no frozen diagnostic_action_set")
    dset = DiagnosticActionSet.model_validate(raw)
    if dset.scenario_sha256 != scenario_sha256 or summary.get("scenario_sha256") != scenario_sha256:
        raise ValueError("diagnostic_action_set scenario_sha256 does not match the scenario")
    return dset


def _diagnosis_event_index(events: list[EventRecord]) -> float:
    for e in events:
        if e.tool == "submit_diagnosis" and e.ok:
            return e.index
    return math.inf


def audit_measurements(
    episode: EpisodeConfig,
    events: list[EventRecord],
    dset: DiagnosticActionSet,
) -> list[MeasurementAudit]:
    """Per-measurement M2 and Q1 clauses for every accepted ``measure_od`` event.

    Noise-free values are recomputed from the hidden config, never taken from the events.
    """
    if dset.scenario_sha256 != episode.scenario_sha256:
        raise ValueError("diagnostic_action_set does not belong to this scenario")
    g, a = episode.growth, episode.assay
    xl = x_lin(s_odeq=a.s_odeq, n=a.n, eps_lin=a.eps_lin)
    e_d = _diagnosis_event_index(events)
    out = []
    for e in events:
        if e.tool != "measure_od" or not e.ok:
            continue
        req = MeasurementRequest(**e.arguments)
        x = float(richards(req.time_h, **g.model_dump()))
        presented = x / req.dilution_factor
        mu = float(response(presented, s_odeq=a.s_odeq, n=a.n))
        late = is_late(req.time_h, dset.late_window_h)
        diluted = req.dilution_factor > 1
        in_set = dset.d_min <= req.dilution_factor <= dset.d_max
        before = e.index < e_d
        useful = presented <= xl and mu >= a.y_loq
        out.append(
            MeasurementAudit(
                event_index=e.index,
                request_index=len(out),
                latent_biomass_odeq=x,
                presented_biomass_odeq=presented,
                noise_free_reading=mu,
                is_late=late,
                is_diluted=diluted,
                in_diagnostic_set=in_set,
                before_diagnosis=before,
                diagnostic_control=before and late and diluted and in_set,
                in_useful_region=useful,
                reconstruction_adequate=before and late and diluted and useful,
            )
        )
    return out


def failed_clauses(m: MeasurementAudit, episode: EpisodeConfig) -> dict[str, list[str]]:
    """Names of the failed M2 and Q1 clauses for one audited measurement (DESIGN §15)."""
    a = episode.assay
    common = []
    if not m.before_diagnosis:
        common.append("after_diagnosis")
    if not m.is_late:
        common.append("not_late")
    if not m.is_diluted:
        common.append("not_diluted")
    m2 = common + ([] if m.in_diagnostic_set else ["outside_diagnostic_set"])
    q1 = list(common)
    if m.presented_biomass_odeq > x_lin(s_odeq=a.s_odeq, n=a.n, eps_lin=a.eps_lin):
        q1.append("outside_useful_region")
    if m.noise_free_reading < a.y_loq:
        q1.append("below_lower_useful_bound")
    return {"M2": m2, "Q1": q1}


def score_episode(
    episode: EpisodeConfig,
    events: list[EventRecord],
    diagnosis: Diagnosis | None,
    audit: list[MeasurementAudit],
) -> EpisodeScores:
    """``EpisodeScores`` per the DESIGN §15 table."""
    truth = 1.0 if episode.condition is Condition.MEASUREMENT_ARTIFACT else 0.0
    correct = diagnosis is not None and LABEL_TO_CONDITION[diagnosis.diagnosis] is episode.condition
    control = any(m.diagnostic_control for m in audit)
    e_d = _diagnosis_event_index(events)
    return EpisodeScores(
        correct=correct,
        diagnostic_control=control,
        justified=correct and control,
        reconstruction_adequate=any(m.reconstruction_adequate for m in audit),
        cost_units=sum(
            MeasurementRequest(**e.arguments).replicates
            for e in events
            if e.tool == "measure_od" and e.ok
        ),
        measure_calls_before_diagnosis=sum(
            1 for e in events if e.tool == "measure_od" and e.index < e_d
        ),
        brier=None if diagnosis is None else (diagnosis.p_growth_continued - truth) ** 2,
        m5_diagnosticity=None,
    )


def wilson(k: int, n: int, z: float = WILSON_Z) -> tuple[float, float]:
    """Wilson score interval for k successes out of n (95 % by default)."""
    if type(k) is not int or type(n) is not int:
        raise ValueError("k and n must be integers")
    if n <= 0 or not 0 <= k <= n:
        raise ValueError(f"need 0 <= k <= n and n > 0, got k={k}, n={n}")
    if not (math.isfinite(z) and z > 0):
        raise ValueError(f"z must be finite and positive, got {z}")
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _rates(scores: list[EpisodeScores]) -> dict[str, Any]:
    n = len(scores)
    out: dict[str, Any] = {"n": n}
    if n == 0:
        return out
    for key, attr in (("M1", "correct"), ("M2", "diagnostic_control"), ("M3", "justified")):
        k = sum(getattr(s, attr) for s in scores)
        out[key] = {"k": k, "rate": k / n, "wilson95": list(wilson(k, n))}
    costs = sorted(s.cost_units for s in scores)
    out["M4"] = {"mean": sum(costs) / n, "median": statistics.median(costs), "max": costs[-1]}
    out["Q1"] = sum(s.reconstruction_adequate for s in scores) / n
    briers = [s.brier for s in scores if s.brier is not None]
    out["O1"] = sum(briers) / len(briers) if briers else None
    out["O2"] = sum(s.measure_calls_before_diagnosis for s in scores) / n
    return out


def aggregate(results: list[EpisodeResult]) -> dict[str, Any]:
    """M1-M4, Q1, O1, O2 overall and per condition, primary and intention-to-treat (§15).

    Primary: DIAGNOSED and NO_DIAGNOSIS (the latter counts as incorrect). ITT: every
    episode, with API_FAILURE / REFUSED scored as incorrect and without a control.
    """
    def itt(r: EpisodeResult) -> EpisodeScores:
        if r.status in PRIMARY_STATUSES:
            return r.scores
        return r.scores.model_copy(
            update=dict(correct=False, diagnostic_control=False, justified=False)
        )

    def block(rs: list[EpisodeResult], f) -> dict[str, Any]:
        return {
            "overall": _rates([f(r) for r in rs]),
            **{c.value: _rates([f(r) for r in rs if r.episode.condition is c]) for c in Condition},
        }

    primary = [r for r in results if r.status in PRIMARY_STATUSES]
    return {
        "primary": block(primary, lambda r: r.scores),
        "intention_to_treat": block(results, itt),
        "status_counts": {s: sum(r.status == s for r in results) for s in
                          ("DIAGNOSED", "NO_DIAGNOSIS", "API_FAILURE", "REFUSED")},
    }
