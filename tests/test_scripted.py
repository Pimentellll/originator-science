from pathlib import Path

import pytest

from mirage.agents.scripted import GOOD_SCIENTIST_NOTES, GoodScientist, PassiveBayesAgent
from mirage.lab.tools import MeasurementResult, Observation, ToolResponse
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


# ---- review fixes (#32) ---------------------------------------------------------------------

class RejectingSession:
    """Visible-session fake whose plateau readings are unequal and which rejects one tool."""

    finished = False

    def __init__(self, reject: str | None = None, plateau=(1.0, 2.0, 3.0, 6.0), y=0.6):
        vals = {15: plateau[0], 16: plateau[1], 17: plateau[2], 18: plateau[3]}
        pr = [MeasurementResult(source="passive", request_index=None, time_h=t, dilution_factor=1.0,
                                readings=[vals.get(t, 100.0)], mean_reading=vals.get(t, 100.0),
                                cost_units=0, budget_remaining=6) for t in range(19)]
        self._obs = Observation(passive_readings=pr, budget_total=6, budget_remaining=6)
        self.reject, self.y, self.calls = reject, y, []

    def observation(self):
        return self._obs

    def call(self, tool, args):
        self.calls.append((tool, args))
        if tool == self.reject:
            return ToolResponse(ok=False, result=None, error=f"{tool}: rejected by test")
        res = {"readings": [self.y] * 3} if tool == "measure_od" else {"status": "ok"}
        return ToolResponse(ok=True, result=res, error=None)


class FixedClassifier:
    def classify(self, readings):
        return "GROWTH_STOPPED", 0.25


@pytest.mark.parametrize("tool", ["declare_state", "measure_od", "submit_diagnosis"])
def test_good_scientist_raises_on_any_rejected_call(tool) -> None:
    s = RejectingSession(reject=tool)
    with pytest.raises(RuntimeError, match=rf"GoodScientist {tool} rejected: {tool}: rejected by test"):
        GoodScientist().run(s)
    assert s.calls[-1][0] == tool  # stops at the rejected call


def test_passive_bayes_raises_on_rejected_submission() -> None:
    s = RejectingSession(reject="submit_diagnosis")
    with pytest.raises(RuntimeError, match="PassiveBayes submit_diagnosis rejected: submit_diagnosis: rejected"):
        PassiveBayesAgent(FixedClassifier()).run(s)


def test_passive_bayes_never_declares_or_measures() -> None:
    # PassiveBayes makes no declare_state call (DESIGN §16.2), so a rejected declaration cannot occur.
    s = RejectingSession(reject="declare_state")
    PassiveBayesAgent(FixedClassifier()).run(s)
    assert [c[0] for c in s.calls] == ["submit_diagnosis"]
    assert s.calls[0][1]["diagnosis"] == "GROWTH_STOPPED" and s.calls[0][1]["p_growth_continued"] == 0.25


def test_good_scientist_plateau_uses_all_four_unequal_readings() -> None:
    # 15-18 h = 1, 2, 3, 10 -> P = 4.0; C = 10 * 0.8 = 8.0 -> R = 2.000.
    # Every three-reading mean (5.0, 4.667, 4.333, 2.0) differs from 4.0.
    plateau = (1.0, 2.0, 3.0, 10.0)
    s = RejectingSession(plateau=plateau, y=0.8)
    GoodScientist().run(s)
    rationale = s.calls[-1][1]["rationale"]
    assert "8.0000 / passive plateau 4.0000 = 2.000 >= 1.5" in rationale
    for drop in range(4):
        kept = [v for i, v in enumerate(plateau) if i != drop]
        assert sum(kept) / 3 != 4.0
        assert f"{sum(kept) / 3:.4f}" not in rationale.split("plateau ")[1]


def test_good_scientist_declaration_note_exact() -> None:
    s = RejectingSession()
    GoodScientist().run(s)
    assert s.calls[0] == ("declare_state", {
        "notes": "Passive data alone cannot separate a real stop from readings that no longer "
                 "track biomass.",
        "p_growth_continued": 0.5})
    assert GOOD_SCIENTIST_NOTES == s.calls[0][1]["notes"]


def test_scripted_agents_are_deterministic(reference) -> None:
    for agent in (GoodScientist(), PassiveBayesAgent(reference)):
        for cond in Condition:
            runs = []
            for _ in range(2):
                env = LabEnvironment(sample_episode(PRIOR, 900_123, cond))
                agent.run(env.session())
                runs.append([e.model_dump() for e in env.events])
            assert runs[0] == runs[1]


SPEC_N = 1_000


@pytest.fixture(scope="module")
def full_reference():
    assert len(REFERENCE_SEEDS) == 200_000
    return build_reference(PRIOR, REFERENCE_SEEDS)


def test_t015_t016_specification_scale(full_reference) -> None:
    """TEST_PLAN scale: 1,000 episodes per condition; PassiveBayes on the 200,000-seed reference."""
    seeds = range(900_000, 900_000 + SPEC_N)
    gs = {c: [s for _, s in play(GoodScientist(), c, seeds)] for c in Condition}
    for c in Condition:
        assert sum(s.correct for s in gs[c]) / SPEC_N >= 0.98
        assert all(s.diagnostic_control for s in gs[c]) and all(s.cost_units == 3 for s in gs[c])
    pb = {c: play(PassiveBayesAgent(full_reference), c, seeds) for c in Condition}
    ba = sum(sum(s.correct for _, s in pb[c]) / SPEC_N for c in Condition) / 2
    assert 0.50 <= ba <= 0.65
    assert all(not any(e.tool == "measure_od" for e in env.events) for c in Condition for env, _ in pb[c])
