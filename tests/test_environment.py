import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from mirage.assay.od_reader import read, response
from mirage.biology.growth import richards
from mirage.config import load_prior, sample_episode
from mirage.lab.environment import LabEnvironment
from mirage.lab.tools import AgentState, Observation, ToolResponse, render_observation

ROOT = Path(__file__).resolve().parents[1]
PRIOR = load_prior(ROOT / "experiments" / "configs" / "scenario_v1.json")


def cfg(seed: int = 7, cond: str = "MEASUREMENT_ARTIFACT"):
    return sample_episode(PRIOR, seed, cond)


def measure(env, t=18, d=10.0, r=1):
    return env.call("measure_od", {"time_h": t, "dilution_factor": d, "replicates": r})


def config_hash(c) -> str:
    return hashlib.sha256(json.dumps(c.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


def test_passive_history_matches_design_7() -> None:
    c = cfg()
    env = LabEnvironment(c)
    a = c.assay
    x = richards(np.arange(19), **c.growth.model_dump())
    rng = np.random.default_rng(np.random.SeedSequence([c.seed, 1]))
    expected = read(x, rng, s_odeq=a.s_odeq, n=a.n, sigma_abs=a.sigma_abs, sigma_rel=a.sigma_rel)
    assert [p.time_h for p in env.passive] == list(range(19))
    assert [p.mean_reading for p in env.passive] == [float(y) for y in expected]
    assert all(p.source == "passive" and p.cost_units == 0 and p.dilution_factor == 1.0
               for p in env.passive)
    assert env.budget_remaining == 6


def test_measurement_uses_stream_seed_2_i() -> None:
    c = cfg()
    env = LabEnvironment(c)
    measure(env, 18, 10.0, 2)
    r = measure(env, 14, 4.0, 3)
    a = c.assay
    x = float(richards(14, **c.growth.model_dump())) / 4.0
    rng = np.random.default_rng(np.random.SeedSequence([c.seed, 2, 1]))
    ys = read(np.full(3, x), rng, s_odeq=a.s_odeq, n=a.n, sigma_abs=a.sigma_abs,
              sigma_rel=a.sigma_rel)
    assert r.ok and r.result["readings"] == [float(y) for y in ys]
    assert r.result["mean_reading"] == round(float(np.mean(ys)), 4)
    assert set(r.result) == {"budget_remaining", "dilution_factor", "mean_reading", "readings",
                             "time_h"}


def test_rejected_requests_consume_no_stream() -> None:
    a, b = LabEnvironment(cfg()), LabEnvironment(cfg())
    measure(a, 18, 200.0, 1)
    a.call("measure_od", {"dilution_factor": 10.0})
    ra, rb = measure(a, 18, 10.0, 3), measure(b, 18, 10.0, 3)
    assert ra.result == rb.result


def test_t011_dilution_changes_the_aliquot_only() -> None:
    c = cfg()
    seq = [(18, 10.0), (18, 1.0), (12, 4.0)]
    env = LabEnvironment(c)
    x_before = [env.latent(t) for t in range(19)]
    for t, d in seq:
        measure(env, t, d)
    for m, (t, d) in zip(env.accepted, seq, strict=True):
        fresh = LabEnvironment(c)
        measure(fresh, t, d)
        f = fresh.accepted[0]
        assert m.presented_biomass_odeq == f.presented_biomass_odeq
        assert m.noise_free_reading == f.noise_free_reading
        assert m.presented_biomass_odeq == m.latent_biomass_odeq / d
        assert m.latent_biomass_odeq == float(richards(t, **c.growth.model_dump()))
    assert [env.latent(t) for t in range(19)] == x_before


def test_t013_budget_accounting() -> None:
    env = LabEnvironment(cfg())
    out = [
        measure(env, 18, 10.0, 3),
        env.call("measure_od", {"time_h": 19, "dilution_factor": 10.0, "replicates": 1}),
        measure(env, 18, 5.0, 2),
        measure(env, 18, 2.0, 2),
        env.call("measure_od", {"time_h": 18, "dilution_factor": 0.5, "replicates": 1}),
        measure(env, 16, 10.0, 1),
    ]
    assert [o.ok for o in out] == [True, False, True, False, False, True]
    assert [o.result["budget_remaining"] for o in out if o.ok] == [3, 1, 0]
    assert out[3].error == "replicates (2) exceeds remaining budget (1)"
    assert [m.replicates for m in env.accepted] == [3, 2, 1]
    assert sum(m.replicates for m in env.accepted) == 6 and env.budget_remaining == 0
    assert all(p.cost_units == 0 for p in env.passive)
    assert not env.finished
    assert env.call("submit_diagnosis", {
        "diagnosis": "BIOMASS_ABOVE_READING",
        "p_biomass_above_reading": 0.9,
        "late_biomass_estimate_od": None,
        "rationale": "x",
    }).ok
    assert env.status == "DIAGNOSED"


INVALID = [
    ("measure_od", {"time_h": -1, "dilution_factor": 10.0, "replicates": 1}),
    ("measure_od", {"time_h": 19, "dilution_factor": 10.0, "replicates": 1}),
    ("measure_od", {"time_h": 2.5, "dilution_factor": 10.0, "replicates": 1}),
    ("measure_od", {"time_h": "18", "dilution_factor": 10.0, "replicates": 1}),
    ("measure_od", {"time_h": 18, "dilution_factor": 0.5, "replicates": 1}),
    ("measure_od", {"time_h": 18, "dilution_factor": 0, "replicates": 1}),
    ("measure_od", {"time_h": 18, "dilution_factor": 101, "replicates": 1}),
    ("measure_od", {"time_h": 18, "dilution_factor": math.nan, "replicates": 1}),
    ("measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": 0}),
    ("measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": 4}),
    ("measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": 1, "extra": 1}),
    ("measure_od", {"dilution_factor": 10.0, "replicates": 1}),
    ("pipette", {"volume": 1}),
    ("submit_diagnosis", {"diagnosis": "BIOLOGICAL_PLATEAU", "p_biomass_above_reading": 0.5,
                          "late_biomass_estimate_od": None, "rationale": "x"}),
    ("declare_state", {"notes": "x", "p_biomass_above_reading": 1.5}),
]


@pytest.mark.parametrize("tool,args", INVALID)
def test_t020_invalid_requests(tool, args) -> None:
    env = LabEnvironment(cfg())
    before = (env.budget_remaining, len(env.accepted), env.diagnosis, env.status)
    r = env.call(tool, args)
    assert isinstance(r, ToolResponse) and not r.ok and r.result is None
    assert r.error and "\n" not in r.error
    ev = env.events[-1]
    assert (ev.ok, ev.error, ev.tool, ev.turn) == (False, r.error, tool, 1)
    assert (env.budget_remaining, len(env.accepted), env.diagnosis, env.status) == before
    # No stream consumed: the next accepted request reads exactly as in a fresh environment.
    assert measure(env).result == measure(LabEnvironment(cfg())).result


def test_integer_dilution_from_json_is_accepted() -> None:
    assert measure(LabEnvironment(cfg()), 18, 10, 1).ok


def test_t026_within_episode_instrument_stability() -> None:
    rng = np.random.default_rng(0)
    for seed in range(100):
        c = cfg(seed, "MEASUREMENT_ARTIFACT" if seed % 2 else "BIOLOGICAL_PLATEAU")
        h = config_hash(c)
        env = LabEnvironment(c)
        for _ in range(6):
            assert measure(env, int(rng.integers(0, 19)), float(rng.uniform(1, 100)), 1).ok
        a = env.config.assay
        for m in env.accepted:
            assert m.noise_free_reading == float(response(m.presented_biomass_odeq,
                                                          s_odeq=c.assay.s_odeq, n=c.assay.n))
        assert a == c.assay and config_hash(env.config) == h
        assert env.budget_remaining == 0


def test_turn_limit_ends_episode_no_diagnosis() -> None:
    env = LabEnvironment(cfg())
    for _ in range(11):
        env.call("declare_state", {"notes": "thinking", "p_biomass_above_reading": 0.5})
    assert not env.finished
    env.call("pipette", {})
    assert env.finished and env.status == "NO_DIAGNOSIS" and env.turn == 12
    with pytest.raises(RuntimeError):
        env.call("declare_state", {"notes": "x", "p_biomass_above_reading": 0.5})


def test_diagnosis_on_last_turn_counts() -> None:
    env = LabEnvironment(cfg())
    for _ in range(11):
        env.call("declare_state", {"notes": "x", "p_biomass_above_reading": 0.5})
    env.call("submit_diagnosis", {"diagnosis": "BIOMASS_AS_READ", "p_biomass_above_reading": 0.1,
                                  "late_biomass_estimate_od": 1.0, "rationale": "flat"})
    assert env.status == "DIAGNOSED" and env.diagnosis is not None


def test_second_finish_raises_and_keeps_first_status() -> None:
    env = LabEnvironment(cfg())
    env.finish("REFUSED")
    with pytest.raises(RuntimeError, match="already finished"):
        env.finish("API_FAILURE")
    assert env.status == "REFUSED" and env.session().finished


def test_finish_after_turn_limit_raises() -> None:
    env = LabEnvironment(cfg(), max_turns=1)
    s = env.session()
    s.call("declare_state", {"notes": "n", "p_biomass_above_reading": 0.5})
    assert env.status == "NO_DIAGNOSIS"
    with pytest.raises(RuntimeError, match="already finished"):
        env.finish("API_FAILURE")
    assert env.status == "NO_DIAGNOSIS"


def test_session_facade_exposes_only_the_protocol() -> None:
    env = LabEnvironment(cfg())
    s = env.session()
    public = {n for n in dir(s) if not n.startswith("_")}
    assert public == {"observation", "call", "finished"}
    assert not hasattr(s, "__dict__")
    obs = s.observation()
    assert isinstance(obs, Observation)
    assert "config" not in render_observation(obs)
    assert s.call("measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": 1}).ok
    assert s.observation().budget_remaining == 5


def test_environment_is_deterministic() -> None:
    def run():
        env = LabEnvironment(cfg(3))
        measure(env, 18, 10.0, 3)
        measure(env, 12, 2.0, 2)
        return [p.mean_reading for p in env.passive], [e.model_dump() for e in env.events]
    assert run() == run()


# ---- review fixes (fix/lab-validation) ------------------------------------------------------

@pytest.mark.parametrize("status", ["bogus", "", "diagnosed", None])
def test_finish_rejects_invalid_status(status) -> None:
    env = LabEnvironment(cfg())
    with pytest.raises(ValueError, match="invalid episode status"):
        env.finish(status)
    assert env.status is None and not env.finished


def test_finish_diagnosed_requires_a_diagnosis() -> None:
    env = LabEnvironment(cfg())
    with pytest.raises(ValueError, match="requires an accepted diagnosis"):
        env.finish("DIAGNOSED")
    assert env.status is None


def test_finish_after_diagnosis_is_rejected_and_status_kept() -> None:
    env = LabEnvironment(cfg())
    assert env.call("submit_diagnosis", {
        "diagnosis": "BIOMASS_AS_READ",
        "p_biomass_above_reading": 0.2,
        "late_biomass_estimate_od": None,
        "rationale": "x",
    }).ok
    with pytest.raises(RuntimeError, match="already finished"):
        env.finish("API_FAILURE")
    assert env.status == "DIAGNOSED"


@pytest.mark.parametrize("status", ["NO_DIAGNOSIS", "API_FAILURE", "REFUSED"])
def test_finish_valid_runner_statuses(status) -> None:
    env = LabEnvironment(cfg())
    env.finish(status)
    assert env.status == status and env.session().finished
    with pytest.raises(RuntimeError, match="finished"):
        env.call("declare_state", {"notes": "x", "p_biomass_above_reading": 0.5})
    assert env.events == []


def test_api_failure_mid_episode_terminates() -> None:
    env = LabEnvironment(cfg())
    assert measure(env).ok
    env.finish("API_FAILURE")
    assert env.status == "API_FAILURE" and env.diagnosis is None and len(env.events) == 1
    with pytest.raises(RuntimeError):
        measure(env)
    assert len(env.events) == 1 and env.budget_remaining == 5


@pytest.mark.parametrize("bad", [0, -1, -12, float("nan"), 1.5, 12.0, True, "12", None])
def test_max_turns_validated_before_observations(bad, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(LabEnvironment, "_passive_history", lambda self: calls.append(1) or [])
    with pytest.raises(ValueError, match="max_turns must be a positive integer"):
        LabEnvironment(cfg(), max_turns=bad)
    assert calls == []


@pytest.mark.parametrize("good", [1, 3, 12])
def test_max_turns_accepts_positive_int(good) -> None:
    env = LabEnvironment(cfg(), max_turns=good)
    for _ in range(good):
        env.call("declare_state", {"notes": "n", "p_biomass_above_reading": 0.5})
    assert env.status == "NO_DIAGNOSIS" and env.turn == good


def test_t026_readings_recomputed_from_each_request_stream() -> None:
    rng = np.random.default_rng(1)
    for seed in range(40):
        c = cfg(seed, "MEASUREMENT_ARTIFACT" if seed % 2 else "BIOLOGICAL_PLATEAU")
        env = LabEnvironment(c)
        reqs = []
        while env.budget_remaining:
            r = int(rng.integers(1, min(3, env.budget_remaining) + 1))
            req = {"time_h": int(rng.integers(0, 19)), "dilution_factor": float(rng.uniform(1, 100)),
                   "replicates": r}
            assert env.call("measure_od", req).ok
            reqs.append(req)
        g, a = c.growth, c.assay
        for i, (req, res) in enumerate(zip(reqs, env.measurements, strict=True)):
            x = float(richards(req["time_h"], k_odeq=g.k_odeq, r_per_h=g.r_per_h,
                               x0_odeq=g.x0_odeq, nu=g.nu))
            stream = np.random.default_rng(np.random.SeedSequence([seed, 2, i]))
            expect = read(np.full(req["replicates"], x / req["dilution_factor"]), stream,
                          s_odeq=a.s_odeq, n=a.n, sigma_abs=a.sigma_abs, sigma_rel=a.sigma_rel)
            assert res.readings == [float(y) for y in expect]
            assert res.request_index == i and res.cost_units == req["replicates"]


def test_every_call_is_one_complete_event() -> None:
    env = LabEnvironment(cfg())
    script = [("measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": 2}),
              ("measure_od", {"time_h": 99}),
              ("declare_state", {"notes": "thinking", "p_biomass_above_reading": 0.4}),
              ("nope", {}),
              ("submit_diagnosis", {
                  "diagnosis": "BIOMASS_ABOVE_READING",
                  "p_biomass_above_reading": 0.9,
                  "late_biomass_estimate_od": 3.2,
                  "rationale": "r",
              })]
    responses = [env.call(t, a) for t, a in script]
    assert [e.index for e in env.events] == list(range(5))
    assert [e.turn for e in env.events] == [1, 2, 3, 4, 5]
    for e, (tool, args), r in zip(env.events, script, responses, strict=True):
        assert (e.tool, e.arguments, e.ok, e.result, e.error) == (tool, args, r.ok, r.result, r.error)
    assert [e.ok for e in env.events] == [True, False, True, False, True]
    assert [m.event_index for m in env.accepted] == [0]
    assert env.agent_states == [AgentState(notes="thinking", p_biomass_above_reading=0.4)]
    assert env.status == "DIAGNOSED" and env.diagnosis.late_biomass_estimate_od == 3.2
