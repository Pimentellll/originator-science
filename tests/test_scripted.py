from pathlib import Path

import pytest

from mirage.agents.scripted import GoodScientist, PassiveBayesAgent
from mirage.biology.conditions import Condition
from mirage.config import canonical_sha256, load_prior, sample_episode
from mirage.evaluation.metrics import DiagnosticActionSet, audit_measurements, score_episode
from mirage.evaluation.passive import REFERENCE_SEEDS, build_reference
from mirage.lab.environment import LabEnvironment

ROOT = Path(__file__).resolve().parents[1]
PRIOR = load_prior(ROOT / "experiments" / "configs" / "scenario_v1.json")
# FIXTURE diagnostic set until Gate 0 freezes D_diag (T-032).
DSET = DiagnosticActionSet(scenario_sha256=canonical_sha256(PRIOR), late_window_h=(12, 18),
                           d_min=1.5, d_max=100.0, auroc_threshold=0.95, evaluated_replicates=1)
N = 300
SEEDS = range(900_000, 900_000 + N)


def play(agent, cond: Condition, seeds=SEEDS):
    out = []
    for seed in seeds:
        cfg = sample_episode(PRIOR, seed, cond)
        env = LabEnvironment(cfg)
        agent.run(env.session())
        audit = audit_measurements(cfg, env.events, DSET)
        out.append((env, score_episode(cfg, env.events, env.diagnosis, audit)))
    return out


@pytest.mark.parametrize("cond", list(Condition))
def test_t015_good_scientist(cond) -> None:
    res = play(GoodScientist(), cond)
    scores = [s for _, s in res]
    assert all(env.status == "DIAGNOSED" for env, _ in res)
    m1 = sum(s.correct for s in scores) / N
    m2 = sum(s.diagnostic_control for s in scores) / N
    m3 = sum(s.justified for s in scores) / N
    m4 = sum(s.cost_units for s in scores) / N
    assert m1 >= 0.98 and m2 == 1.0 and m3 >= 0.98 and m4 == 3.0
    assert all(s.reconstruction_adequate for s in scores)


def test_good_scientist_protocol_exact() -> None:
    env = LabEnvironment(sample_episode(PRIOR, 7, Condition.MEASUREMENT_ARTIFACT))
    GoodScientist().run(env.session())
    tools = [(e.tool, e.ok) for e in env.events]
    assert tools == [("declare_state", True), ("measure_od", True), ("submit_diagnosis", True)]
    assert env.events[0].arguments["p_growth_continued"] == 0.5
    assert env.events[1].arguments == {"time_h": 18, "dilution_factor": 10.0, "replicates": 3}
    p_hat = sum(m.mean_reading for m in env.passive if m.time_h in (15, 16, 17, 18)) / 4
    c_hat = 10 * sum(env.measurements[0].readings) / 3
    d = env.diagnosis
    assert d.late_biomass_estimate_od == pytest.approx(c_hat, rel=1e-12)
    assert (d.diagnosis == "GROWTH_CONTINUED") == (c_hat / p_hat >= 1.5)
    assert d.p_growth_continued == (0.99 if d.diagnosis == "GROWTH_CONTINUED" else 0.01)


def test_good_scientist_threshold_is_tau() -> None:
    class Fake:
        def __init__(self, y):
            from mirage.lab.tools import MeasurementResult, Observation, ToolResponse
            self.calls = []
            pr = [MeasurementResult(source="passive", request_index=None, time_h=t, dilution_factor=1.0,
                                    readings=[1.0], mean_reading=1.0, cost_units=0, budget_remaining=6)
                  for t in range(19)]
            self._obs = Observation(passive_readings=pr, budget_total=6, budget_remaining=6)
            self._y, self._TR = y, ToolResponse

        def observation(self):
            return self._obs

        def call(self, tool, args):
            self.calls.append((tool, args))
            res = {"readings": [self._y] * 3} if tool == "measure_od" else {"status": "ok"}
            return self._TR(ok=True, result=res, error=None)

        finished = False

    for y, label in ((0.15, "GROWTH_CONTINUED"), (0.1499, "GROWTH_STOPPED")):
        s = Fake(y)
        GoodScientist().run(s)
        assert s.calls[-1][1]["diagnosis"] == label


@pytest.fixture(scope="module")
def reference():
    return build_reference(PRIOR, REFERENCE_SEEDS[:20_000])


def test_t016_passive_bayes(reference) -> None:
    acc, cost = {}, 0
    for cond in Condition:
        res = play(PassiveBayesAgent(reference), cond)
        for env, s in res:
            assert not any(e.tool == "measure_od" for e in env.events)
            assert not s.diagnostic_control and not s.justified
            cost += s.cost_units
        acc[cond] = sum(s.correct for _, s in res) / N
    ba = sum(acc.values()) / 2
    assert 0.50 <= ba <= 0.65 and cost == 0


def test_good_scientist_uses_15_to_18_h_plateau() -> None:
    from mirage.lab.tools import MeasurementResult, Observation, ToolResponse

    class S:
        finished = False

        def __init__(self):
            # passive 1.0 at 15-18 h, 100.0 elsewhere: only the 15-18 h mean gives P = 1.
            pr = [MeasurementResult(source="passive", request_index=None, time_h=t, dilution_factor=1.0,
                                    readings=[v], mean_reading=v, cost_units=0, budget_remaining=6)
                  for t in range(19) for v in [1.0 if 15 <= t <= 18 else 100.0]]
            self._obs = Observation(passive_readings=pr, budget_total=6, budget_remaining=6)
            self.calls = []

        def observation(self):
            return self._obs

        def call(self, tool, args):
            self.calls.append((tool, args))
            return ToolResponse(ok=True, result={"readings": [0.2, 0.2, 0.2]}, error=None)

    s = S()
    GoodScientist().run(s)
    assert s.calls[-1][1]["diagnosis"] == "GROWTH_CONTINUED"  # R = 2.0 / 1.0
    assert "= 2.000" in s.calls[-1][1]["rationale"]


def test_passive_bayes_agent_reports_classifier_output(reference) -> None:
    for seed in range(20):
        env = LabEnvironment(sample_episode(PRIOR, seed, Condition.BIOLOGICAL_PLATEAU))
        PassiveBayesAgent(reference).run(env.session())
        label, p = reference.classify([m.mean_reading for m in env.passive])
        assert env.diagnosis.diagnosis == label and env.diagnosis.p_growth_continued == p
