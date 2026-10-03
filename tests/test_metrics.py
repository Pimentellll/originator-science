import ast
import inspect
import itertools
import json
from pathlib import Path

import pytest

from mirage.biology.conditions import Condition
from mirage.config import EpisodeConfig, load_demo_pair, load_prior, sample_episode
from mirage.evaluation import metrics
from mirage.evaluation.metrics import (
    DiagnosticActionSet,
    EpisodeResult,
    EventRecord,
    aggregate,
    audit_measurements,
    failed_clauses,
    is_late,
    load_diagnostic_action_set,
    score_episode,
    wilson,
)
from mirage.lab.tools import Diagnosis

ROOT = Path(__file__).resolve().parents[1]
PRIOR = load_prior(ROOT / "experiments" / "configs" / "scenario_v1.json")
BP_DEMO, MA_DEMO = load_demo_pair(ROOT / "experiments" / "configs" / "demo_pair.json", PRIOR,
                                  seeds=(0, 1))
SHA = BP_DEMO.scenario_sha256


def dset(d_min: float = 1.5, d_max: float = 100.0, sha: str = SHA) -> DiagnosticActionSet:
    return DiagnosticActionSet(scenario_sha256=sha, late_window_h=(12, 18), d_min=d_min,
                               d_max=d_max, auroc_threshold=0.95, evaluated_replicates=1)


def ev_measure(i: int, t: int, d: float, reps: int = 1, ok: bool = True) -> EventRecord:
    return EventRecord(index=i, turn=i + 1, tool="measure_od",
                       arguments={"time_h": t, "dilution_factor": d, "replicates": reps},
                       ok=ok, result={} if ok else None, error=None if ok else "rejected")


def ev_diag(i: int, label: str = "BIOMASS_ABOVE_READING", p: float = 0.9) -> EventRecord:
    return EventRecord(index=i, turn=i + 1, tool="submit_diagnosis",
                       arguments={"diagnosis": label, "p_biomass_above_reading": p,
                                  "late_biomass_estimate_od": None, "rationale": "r"},
                       ok=True, result={"status": "received"}, error=None)


T021 = [
    # case, condition, t, d, after_diagnosis, M2, Q1, M2 clauses, Q1 clauses
    ("a", "MA", 4, 10, False, False, False, ["not_late"], ["not_late"]),
    ("b", "MA", 18, 1, False, False, False, ["not_diluted"],
      ["not_diluted", "outside_useful_region"]),
    ("c", "MA", 18, 2, False, True, False, [], ["outside_useful_region"]),
    ("d", "BP", 18, 50, False, True, False, [], ["below_lower_useful_bound"]),
    ("e", "BP", 18, 10, False, True, True, [], []),
    ("f", "MA", 18, 10, False, True, True, [], []),
    ("g", "MA", 12, 10, False, True, True, [], []),
    ("h", "MA", 18, 10, True, False, False, ["after_diagnosis"], ["after_diagnosis"]),
    ("i", "BP", 18, 2, False, True, True, [], []),
    ("j", "MA", 11, 10, False, False, False, ["not_late"], ["not_late"]),
    ("k", "MA", 18, 1.2, False, False, False, ["outside_diagnostic_set"],
      ["outside_useful_region"]),
]


@pytest.mark.parametrize("case,cond,t,d,after,m2,q1,m2c,q1c", T021, ids=[c[0] for c in T021])
def test_t021_m2_and_q1_rules(case, cond, t, d, after, m2, q1, m2c, q1c) -> None:
    ep = BP_DEMO if cond == "BP" else MA_DEMO
    events = [ev_diag(0), ev_measure(1, t, d)] if after else [ev_measure(0, t, d), ev_diag(1)]
    (m,) = audit_measurements(ep, events, dset())
    assert (m.diagnostic_control, m.reconstruction_adequate) == (m2, q1)
    fc = failed_clauses(m, ep)
    # The table names the decisive clause; the audit records every failed clause.
    assert set(m2c) <= set(fc["M2"]) and set(q1c) <= set(fc["Q1"])
    assert (fc["M2"] == []) == m2 and (fc["Q1"] == []) == q1


def test_t021_m2_never_consults_useful_region() -> None:
    # Same visible action in both demo worlds -> same M2 flag, though Q1 differs (case c vs i).
    for t, d in itertools.product(range(19), [1, 1.2, 1.5, 2, 5, 10, 50, 100]):
        a = audit_measurements(BP_DEMO, [ev_measure(0, t, d)], dset())[0]
        b = audit_measurements(MA_DEMO, [ev_measure(0, t, d)], dset())[0]
        assert a.diagnostic_control == b.diagnostic_control


def test_t027_lateness_uses_only_clock_time() -> None:
    early = sample_episode(PRIOR, 0, "BIOLOGICAL_PLATEAU")
    late = sample_episode(PRIOR, 0, "MEASUREMENT_ARTIFACT")
    for t in range(19):
        fa = audit_measurements(early, [ev_measure(0, t, 10)], dset(sha=early.scenario_sha256))[0]
        fb = audit_measurements(late, [ev_measure(0, t, 10)], dset(sha=late.scenario_sha256))[0]
        assert fa.is_late == fb.is_late == (12 <= t <= 18) == is_late(t, (12, 18))
    assert list(inspect.signature(is_late).parameters) == ["time_h", "late_window_h"]


def write_summary(tmp: Path, ds: dict | None, sha: str = SHA) -> Path:
    p = tmp / "summary.json"
    body = {"schema_version": "gate0-summary-v2", "scenario_sha256": sha}
    if ds is not None:
        body["diagnostic_action_set"] = ds
    p.write_text(json.dumps(body), encoding="utf-8")
    return p


def test_t032_m2_uses_frozen_set_and_is_condition_symmetric(tmp_path: Path) -> None:
    good = dset().model_dump(mode="json")
    ds = load_diagnostic_action_set(write_summary(tmp_path, good), SHA)
    events = [ev_measure(0, 18, 1.2), ev_measure(1, 18, 2), ev_measure(2, 13, 10),
              ev_measure(3, 6, 10), ev_measure(4, 18, 100), ev_diag(5)]
    flags = {ep.condition: [m.diagnostic_control for m in audit_measurements(ep, events, ds)]
             for ep in (BP_DEMO, MA_DEMO)}
    assert flags[BP_DEMO.condition] == flags[MA_DEMO.condition] == [False, True, True, False, True]
    narrow = dset(d_min=5, d_max=20)
    assert [m.diagnostic_control for m in audit_measurements(MA_DEMO, events, narrow)] == [
        False, False, True, False, False]
    with pytest.raises(ValueError):
        load_diagnostic_action_set(write_summary(tmp_path, None), SHA)
    with pytest.raises(ValueError):
        load_diagnostic_action_set(write_summary(tmp_path, dict(good, d_min=None)), SHA)
    with pytest.raises(ValueError):
        load_diagnostic_action_set(
            write_summary(tmp_path, dict(good, scenario_sha256="0" * 64)), SHA
        )
    with pytest.raises(ValueError):
        load_diagnostic_action_set(write_summary(tmp_path, good, sha="0" * 64), SHA)
    with pytest.raises(ValueError):
        audit_measurements(MA_DEMO, events, dset(sha="0" * 64))


@pytest.mark.parametrize(
    "cond,label,control,recon",
    list(itertools.product(["BP", "MA"], ["BIOMASS_AS_READ", "BIOMASS_ABOVE_READING", None],
                           [True, False], [True, False])),
)
def test_t014_diagnosis_scoring_truth_table(cond, label, control, recon) -> None:
    ep = BP_DEMO if cond == "BP" else MA_DEMO
    # (t, d) choices realising each (control, recon) combination in this world.
    if control and recon:
        meas = [(18, 10)]
    elif control:
        meas = [(18, 50)] if cond == "BP" else [(18, 2)]
    elif recon:
        if cond == "MA":
            pytest.skip("impossible in MA: d in (1, 1.5) leaves X/d above x_lin")
        meas = [(18, 1.2)]
    else:
        meas = [(4, 10)]
    events = [ev_measure(i, t, d) for i, (t, d) in enumerate(meas)]
    diag = None
    if label is not None:
        events.append(ev_diag(len(events), label, 0.7))
        diag = Diagnosis(diagnosis=label, p_biomass_above_reading=0.7, rationale="r")
    audit = audit_measurements(ep, events, dset())
    s = score_episode(ep, events, diag, audit)
    truth = "BIOMASS_AS_READ" if cond == "BP" else "BIOMASS_ABOVE_READING"
    assert s.correct == (label == truth)
    assert s.diagnostic_control == control
    assert s.reconstruction_adequate == recon
    assert s.justified == (s.correct and control)
    if label is None:
        assert s.brier is None
    else:
        assert s.brier == pytest.approx((0.7 - (cond == "MA")) ** 2)


def test_t014_recon_without_control_and_justified_independent_of_q1() -> None:
    # d = 1.2 is outside the fixture D_diag but BP 1.03/1.2 is in the useful region.
    events = [ev_measure(0, 18, 1.2), ev_diag(1, "BIOMASS_AS_READ", 0.1)]
    audit = audit_measurements(BP_DEMO, events, dset())
    s = score_episode(BP_DEMO, events, Diagnosis(diagnosis="BIOMASS_AS_READ",
                                                 p_biomass_above_reading=0.1, rationale="r"), audit)
    assert (s.correct, s.diagnostic_control, s.reconstruction_adequate, s.justified) == (
        True, False, True, False)


def test_cost_and_calls_count() -> None:
    events = [ev_measure(0, 18, 10, 3), ev_measure(1, 18, 200, 1, ok=False),
              ev_measure(2, 14, 5, 2), ev_diag(3)]
    audit = audit_measurements(MA_DEMO, events, dset())
    s = score_episode(MA_DEMO, events, None, audit)
    assert s.cost_units == 5 and s.measure_calls_before_diagnosis == 3
    assert [m.request_index for m in audit] == [0, 1] and [m.event_index for m in audit] == [0, 2]


def test_fixture_record_rescores_identically() -> None:
    rec = EpisodeResult.model_validate_json(
        (ROOT / "tests" / "fixtures" / "sample_episode_llm.json").read_text(encoding="utf-8"))
    ds = dset(sha=rec.episode.scenario_sha256)
    audit = audit_measurements(rec.episode, rec.events, ds)
    assert audit == rec.audit
    assert score_episode(rec.episode, rec.events, rec.diagnosis, audit) == rec.scores


@pytest.mark.parametrize("k,n,lo,hi", [(8, 10, 0.4902, 0.9433), (0, 10, 0.0, 0.2775),
                                       (10, 10, 0.7225, 1.0)])
def test_t023_wilson(k, n, lo, hi) -> None:
    a, b = wilson(k, n)
    assert a == pytest.approx(lo, abs=1e-4) and b == pytest.approx(hi, abs=1e-4)


def _result(ep: EpisodeConfig, status: str, label: str | None, meas) -> EpisodeResult:
    events = [ev_measure(i, t, d, r) for i, (t, d, r) in enumerate(meas)]
    diag = None
    if label:
        events.append(ev_diag(len(events), label, 0.8))
        diag = Diagnosis(diagnosis=label, p_biomass_above_reading=0.8, rationale="r")
    audit = audit_measurements(ep, events, dset(sha=ep.scenario_sha256))
    from mirage.evaluation.metrics import AgentInfo
    return EpisodeResult(
        schema_version="episode-result-v2", episode=ep,
        agent=AgentInfo(name="t", kind="scripted", model=None, effort=None, prompt_version=None,
                        prompt_sha256=None, sdk_version=None),
        passive=[], events=events, diagnosis=diag, status=status, audit=audit,
        scores=score_episode(ep, events, diag, audit), llm_transcript=None, versions={},
        run_meta={})


def test_aggregate_hand_computed() -> None:
    rs = [
        _result(
            MA_DEMO, "DIAGNOSED", "BIOMASS_ABOVE_READING", [(18, 10, 3)]
        ),  # correct, justified
        _result(MA_DEMO, "DIAGNOSED", "BIOMASS_AS_READ", [(18, 1, 2)]),      # wrong, no control
        _result(BP_DEMO, "DIAGNOSED", "BIOMASS_AS_READ", []),                # correct, no control
        _result(BP_DEMO, "NO_DIAGNOSIS", None, [(18, 10, 1)]),              # incorrect, control
        _result(MA_DEMO, "API_FAILURE", None, [(18, 10, 3)]),               # excluded / ITT
    ]
    agg = aggregate(rs)
    p = agg["primary"]["overall"]
    assert p["n"] == 4
    assert (p["M1"]["k"], p["M2"]["k"], p["M3"]["k"]) == (2, 2, 1)
    assert p["M1"]["wilson95"] == list(wilson(2, 4))
    assert p["M4"] == {"mean": 1.5, "median": 1.5, "max": 3}
    assert p["Q1"] == 0.5
    assert p["O1"] == pytest.approx((0.2**2 + 0.2**2 + 0.8**2) / 3)
    assert p["O2"] == pytest.approx(0.75)
    assert agg["primary"]["MEASUREMENT_ARTIFACT"]["n"] == 2
    assert agg["primary"]["BIOLOGICAL_PLATEAU"]["M1"]["k"] == 1
    itt = agg["intention_to_treat"]["overall"]
    assert itt["n"] == 5 and itt["M1"]["k"] == 2 and itt["M2"]["k"] == 2
    assert agg["status_counts"] == {"DIAGNOSED": 3, "NO_DIAGNOSIS": 1, "API_FAILURE": 1,
                                    "REFUSED": 0}


def test_no_anthropic_import_under_evaluation() -> None:
    for path in Path(metrics.__file__).parent.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not any(m.split(".")[0] == "anthropic" for m in mods), path


# ---- review fixes (fix/evaluator-consistency) -----------------------------------------------

@pytest.mark.parametrize("k,n,kw", [(-1, 10, {}), (11, 10, {}), (1.5, 10, {}), (True, 10, {}),
                                    (5, 0, {}), (5, 10.0, {}), (5, 10, {"z": float("nan")}),
                                    (5, 10, {"z": 0.0}), (5, 10, {"z": -1.96}),
                                    (5, 10, {"z": float("inf")})])
def test_wilson_rejects_invalid_inputs(k, n, kw) -> None:
    with pytest.raises(ValueError):
        wilson(k, n, **kw)


@pytest.mark.parametrize("k,n", [(5, 10), (1, 3), (29, 30), (0, 1), (1, 1)])
def test_wilson_matches_independent_formula(k, n) -> None:
    z = 1.959963984540054
    p = k / n
    c = (2 * k + z * z) / (2 * (n + z * z))
    h = z * (n * p * (1 - p) + z * z / 4) ** 0.5 / (n + z * z)
    lo, hi = wilson(k, n)
    assert lo == pytest.approx(max(0.0, c - h), abs=1e-12)
    assert hi == pytest.approx(min(1.0, c + h), abs=1e-12)
    assert 0 <= lo <= p <= hi <= 1


def test_aggregate_itt_refused_and_per_condition() -> None:
    rs = [
        _result(
            MA_DEMO, "DIAGNOSED", "BIOMASS_ABOVE_READING", [(18, 10, 2)]
        ),  # correct, justified
        _result(BP_DEMO, "REFUSED", None, [(18, 10, 1)]),                   # ITT: no control
        _result(
            BP_DEMO, "DIAGNOSED", "BIOMASS_ABOVE_READING", [(18, 10, 1), (18, 1, 1)]
        ),  # wrong
    ]
    agg = aggregate(rs)
    assert agg["primary"]["overall"]["n"] == 2
    bp_p = agg["primary"]["BIOLOGICAL_PLATEAU"]
    assert bp_p["n"] == 1 and bp_p["M1"]["k"] == 0 and bp_p["M2"]["k"] == 1 and bp_p["M3"]["k"] == 0
    assert bp_p["M4"] == {"mean": 2, "median": 2, "max": 2}
    assert bp_p["O1"] == pytest.approx(0.8 ** 2)
    itt_bp = agg["intention_to_treat"]["BIOLOGICAL_PLATEAU"]
    assert itt_bp["n"] == 2 and itt_bp["M1"]["k"] == 0 and itt_bp["M2"]["k"] == 1
    assert itt_bp["M4"] == {"mean": 1.5, "median": 1.5, "max": 2}
    assert itt_bp["O1"] == pytest.approx(0.8 ** 2)
    assert agg["primary"]["MEASUREMENT_ARTIFACT"]["M3"] == {
        "k": 1, "rate": 1.0, "wilson95": list(wilson(1, 1))}
    assert agg["status_counts"]["REFUSED"] == 1
    assert aggregate([])["primary"]["overall"] == {"n": 0}


T021_FLAGS = {
    # case: (is_late, is_diluted, in_diagnostic_set, before_diagnosis)
    "a": (False, True, True, True), "b": (True, False, False, True),
    "c": (True, True, True, True), "d": (True, True, True, True),
    "h": (True, True, True, False),
}


@pytest.mark.parametrize("case", sorted(T021_FLAGS))
def test_audit_flags_independently(case) -> None:
    _, cond, t, d, after, m2, q1, _, _ = next(c for c in T021 if c[0] == case)
    ep = MA_DEMO if cond == "MA" else BP_DEMO
    events = [ev_measure(0, 0, 1.0), ev_measure(1, t, float(d), ok=True)]
    events.insert(0 if after else 2, ev_diag(0))
    events = [e.model_copy(update={"index": i, "turn": i + 1}) for i, e in enumerate(events)]
    audit = audit_measurements(ep, events, dset())
    m = audit[-1]
    assert (m.is_late, m.is_diluted, m.in_diagnostic_set, m.before_diagnosis) == T021_FLAGS[case]
    assert [a.request_index for a in audit] == [0, 1]
    assert (m.diagnostic_control, m.reconstruction_adequate) == (m2, q1)


def test_measure_calls_before_diagnosis_counts_rejected_and_excludes_after() -> None:
    events = [ev_measure(0, 18, 10.0), ev_measure(1, 18, 10.0, ok=False), ev_diag(2),
              ev_measure(3, 18, 10.0)]
    audit = audit_measurements(MA_DEMO, events, dset())
    diag = Diagnosis(diagnosis="BIOMASS_ABOVE_READING", p_biomass_above_reading=0.9, rationale="r")
    s = score_episode(MA_DEMO, events, diag, audit)
    assert s.measure_calls_before_diagnosis == 2 and s.cost_units == 2
    assert [a.before_diagnosis for a in audit] == [True, False]


@pytest.mark.parametrize(
    "cond,label,meas",
    list(
        itertools.product(
            [MA_DEMO, BP_DEMO],
            ["BIOMASS_ABOVE_READING", "BIOMASS_AS_READ"],
            [[(18, 10, 1)], [(18, 1, 1)]],
        )
    ),
)
def test_m3_is_correct_and_m2(cond, label, meas) -> None:
    s = _result(cond, "DIAGNOSED", label, meas).scores
    assert s.justified == (s.correct and s.diagnostic_control)


def test_itt_clears_control_for_api_failure_and_refused_pinned() -> None:
    # NEEDS RULING (DESIGN §15): pins current behaviour; preserving control would give 3/5.
    rs = [
        _result(MA_DEMO, "DIAGNOSED", "BIOMASS_ABOVE_READING", [(18, 10, 3)]),
        _result(MA_DEMO, "DIAGNOSED", "BIOMASS_AS_READ", [(18, 1, 2)]),
        _result(BP_DEMO, "DIAGNOSED", "BIOMASS_AS_READ", []),
        _result(BP_DEMO, "NO_DIAGNOSIS", None, [(18, 10, 1)]),
        _result(MA_DEMO, "API_FAILURE", None, [(18, 10, 3)]),
    ]
    itt = aggregate(rs)["intention_to_treat"]["overall"]
    assert itt["M2"]["k"] == 2 and itt["n"] == 5
    assert itt["M2"]["wilson95"] == list(wilson(2, 5))
    assert itt["M3"]["k"] == 1
    assert itt["M4"] == {"mean": 9 / 5, "median": 2, "max": 3}
    assert itt["Q1"] == pytest.approx(3 / 5)
    assert itt["O1"] == pytest.approx((0.2**2 + 0.2**2 + 0.8**2) / 3)
    assert itt["O2"] == pytest.approx(4 / 5)
    ma = aggregate(rs)["primary"]["MEASUREMENT_ARTIFACT"]
    assert ma["Q1"] == 0.5 and ma["M1"]["rate"] == 0.5


def test_aggregate_absent_condition() -> None:
    agg = aggregate([_result(MA_DEMO, "DIAGNOSED", "BIOMASS_ABOVE_READING", [(18, 10, 1)])])
    assert agg["primary"]["BIOLOGICAL_PLATEAU"] == {"n": 0}
    assert agg["intention_to_treat"]["BIOLOGICAL_PLATEAU"] == {"n": 0}
    assert agg["primary"]["MEASUREMENT_ARTIFACT"]["n"] == 1


def test_fixture_readings_recomputed_from_claimed_streams() -> None:
    import numpy as np

    from mirage.assay.od_reader import read
    from mirage.biology.growth import richards

    rec = EpisodeResult.model_validate_json(
        (ROOT / "tests" / "fixtures" / "sample_episode_llm.json").read_text(encoding="utf-8"))
    assert rec.episode.seed == 7
    g, a = rec.episode.growth, rec.episode.assay
    kw = dict(s_odeq=a.s_odeq, n=a.n, sigma_abs=a.sigma_abs, sigma_rel=a.sigma_rel)
    x = richards(np.arange(19, dtype=float), **g.model_dump())
    passive = read(x, np.random.default_rng(np.random.SeedSequence([7, 1])), **kw)
    assert [p.readings[0] for p in rec.passive] == [float(v) for v in passive]
    assert all(p.mean_reading == p.readings[0] for p in rec.passive)
    ev = rec.events[0]
    args = ev.arguments
    x18 = float(richards(args["time_h"], **g.model_dump()))
    reps = read(np.full(args["replicates"], x18 / args["dilution_factor"]),
                np.random.default_rng(np.random.SeedSequence([7, 2, 0])), **kw)
    assert ev.result["readings"] == [float(v) for v in reps]
    assert ev.result["mean_reading"] == round(float(np.mean(reps)), 4) == 0.4045
    assert ev.result["budget_remaining"] == 6 - args["replicates"] == 3


# ---- legitimate edge records built by LabEnvironment still validate ---------------------------

def _env_record(env) -> EpisodeResult:
    fixture = Path(__file__).parent / "fixtures" / "sample_episode_llm.json"
    base = json.loads(fixture.read_text())
    events = [EventRecord.model_validate(e.model_dump()) for e in env.events]
    audit = metrics.audit_measurements(env.config, events, dset(sha=env.config.scenario_sha256))
    scores = metrics.score_episode(env.config, events, env.diagnosis, audit)
    d = {**base, "episode": env.config.model_dump(mode="json"),
         "events": [e.model_dump(mode="json") for e in events],
         "diagnosis": None if env.diagnosis is None else env.diagnosis.model_dump(mode="json"),
         "status": env.status, "audit": [m.model_dump(mode="json") for m in audit],
         "scores": scores.model_dump(mode="json")}
    return EpisodeResult.model_validate_json(json.dumps(d))


def _diag(p: float = 0.9) -> dict:
    return {"diagnosis": "BIOMASS_ABOVE_READING", "p_biomass_above_reading": p,
            "late_biomass_estimate_od": None, "rationale": "r"}


def _late(reps: int = 3) -> dict:
    return {"time_h": 18, "dilution_factor": 10.0, "replicates": reps}


def _turn_limit(s):
    s.call("declare_state", {"notes": "n", "p_biomass_above_reading": 0.5})
    s.call("declare_state", {"notes": "n", "p_biomass_above_reading": 0.5})


def _over_budget(s):
    s.call("measure_od", _late(3)); s.call("measure_od", _late(3)); s.call("measure_od", _late(1))
    s.call("submit_diagnosis", _diag())


def _rejected_submit_then_more(s):
    s.call("submit_diagnosis", {"diagnosis": "MAYBE"})
    s.call("measure_od", _late(1))
    s.call("declare_state", {"notes": "n", "p_biomass_above_reading": 0.5})
    s.call("no_such_tool", {}); s.call("submit_diagnosis", _diag(1 / 3))


def _diagnose_on_last_turn(s):
    s.call("declare_state", {"notes": "n", "p_biomass_above_reading": 0.5})
    s.call("submit_diagnosis", _diag(0.123456789))


EDGE = {
    "no_diagnosis_at_turn_limit": (_turn_limit, None, "NO_DIAGNOSIS"),
    "over_budget_rejections": (_over_budget, None, "DIAGNOSED"),
    "api_failure_after_measurement": (lambda s: s.call("measure_od", _late()), "API_FAILURE",
                                      "API_FAILURE"),
    "refused_after_measurement": (lambda s: s.call("measure_od", _late()), "REFUSED", "REFUSED"),
    "rejected_submit_then_more_events": (_rejected_submit_then_more, None, "DIAGNOSED"),
    "empty_refused_episode": (lambda s: None, "REFUSED", "REFUSED"),
    "diagnosis_on_last_turn": (_diagnose_on_last_turn, None, "DIAGNOSED"),
}


@pytest.mark.parametrize("name", sorted(EDGE))
def test_legitimate_environment_records_validate(name: str) -> None:
    from mirage.lab.environment import LabEnvironment

    play, finish, status = EDGE[name]
    env = LabEnvironment(sample_episode(PRIOR, 7, Condition.MEASUREMENT_ARTIFACT),
                         max_turns=2 if name in ("no_diagnosis_at_turn_limit",
                                                 "diagnosis_on_last_turn") else 12)
    play(env.session())
    if finish is not None:
        env.finish(finish)
    r = _env_record(env)
    assert r.status == status
