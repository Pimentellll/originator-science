"""Tests for the exploratory grader red-team (experiments/exploratory/grader-redteam).

Dev seeds only (0-9999). The PassiveBayes reference uses a small seed range so the
module-scoped fixtures stay fast.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from itertools import pairwise
from pathlib import Path

import pytest

from mirage.biology.conditions import Condition
from mirage.config import load_prior, sample_episode
from mirage.evaluation import metrics, runner
from mirage.evaluation.passive import build_reference
from mirage.lab.environment import LabEnvironment

ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / "experiments" / "exploratory" / "grader-redteam"


def _load_module(name: str, filename: str):
    module_name = f"exp_grader_redteam_{name}"
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    path = EXP / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


driver = _load_module("driver", "driver.py")
agents = _load_module("agents", "agents.py")
rescore = _load_module("rescore", "rescore.py")

ABOVE, AS_READ = "BIOMASS_ABOVE_READING", "BIOMASS_AS_READ"
DEV_SEEDS = (0, 1)  # 0 = BP, 1 = MA


@pytest.fixture(scope="module")
def prior():
    return load_prior(runner.SCENARIO)


@pytest.fixture(scope="module")
def classifier(prior):
    return build_reference(prior, range(1_000_000, 1_002_000))


@pytest.fixture(scope="module")
def agent_map(prior, classifier):
    return agents.make_agents(classifier, rescore.tau(1.1, prior))


@pytest.fixture(scope="module")
def dset(prior):
    return runner.frozen_dset(prior, runner.GATE0_SUMMARY)


def _cond(seed: int) -> Condition:
    return (
        Condition.BIOLOGICAL_PLATEAU
        if seed % 2 == 0
        else Condition.MEASUREMENT_ARTIFACT
    )


def _run(prior, dset, agent, seed: int):
    cfg = sample_episode(prior, seed, _cond(seed))
    return runner.run_episode(cfg, agent, dset, {"run_id": "t"})


@pytest.fixture(scope="module")
def records(prior, dset, agent_map):
    return {
        (name, seed): _run(prior, dset, agent, seed)
        for name, agent in agent_map.items()
        for seed in DEV_SEEDS
    }


# --- rescore.tau -----------------------------------------------------------


def test_tau_values_and_monotonicity(prior):
    assert rescore.tau(10.0, prior) == pytest.approx(1.77, abs=0.01)
    assert 1.02 <= rescore.tau(1.1, prior) <= 1.10
    ds = [1.1, 1.25, 1.5, 2, 3, 5, 10, 20, 50, 100]
    taus = [rescore.tau(d, prior) for d in ds]
    assert all(b >= a for a, b in pairwise(taus))


# --- rescore.evidence_label ------------------------------------------------


def test_evidence_label():
    ev = lambda label: {"label": label}
    assert rescore.evidence_label([]) is None
    assert rescore.evidence_label([ev(ABOVE), ev(ABOVE), ev(AS_READ)]) == ABOVE
    assert rescore.evidence_label([ev(ABOVE), ev(AS_READ)]) == "TIE"


# --- agents through the frozen runner --------------------------------------


def test_adv_token_above(records):
    for seed in DEV_SEEDS:
        r = records[("adv_token_above", seed)]
        assert r.diagnosis.diagnosis == ABOVE
        assert r.scores.diagnostic_control is True
        assert r.scores.cost_units == 1
        assert r.scores.reconstruction_adequate is True
        assert r.diagnosis.late_biomass_estimate_od is None


def test_adv_token_asread(records):
    for seed in DEV_SEEDS:
        assert records[("adv_token_asread", seed)].diagnosis.diagnosis == AS_READ


def test_adv_nondiag_spend(records):
    for seed in DEV_SEEDS:
        r = records[("adv_nondiag_spend", seed)]
        assert r.scores.diagnostic_control is False
        assert r.scores.cost_units == 6


def test_adv_contrarian(records):
    for seed in DEV_SEEDS:
        gs = records[("ref_good_scientist", seed)].diagnosis.diagnosis
        assert records[("adv_contrarian", seed)].diagnosis.diagnosis != gs


def test_adv_p_mismatch(records):
    for seed in DEV_SEEDS:
        gs = records[("ref_good_scientist", seed)].diagnosis
        r = records[("adv_p_mismatch", seed)].diagnosis
        assert r.diagnosis == gs.diagnosis
        assert r.p_biomass_above_reading == pytest.approx(
            1.0 - gs.p_biomass_above_reading
        )


def test_adv_hedge(records):
    for seed in DEV_SEEDS:
        assert records[("adv_hedge", seed)].diagnosis.p_biomass_above_reading == 0.5


def test_adv_absurd_estimate(records):
    for seed in DEV_SEEDS:
        assert (
            records[("adv_absurd_estimate", seed)].diagnosis.late_biomass_estimate_od
            == 1000.0
        )


def test_adv_extreme_passive(records):
    for seed in DEV_SEEDS:
        r = records[("adv_extreme_passive", seed)]
        assert r.diagnosis.p_biomass_above_reading in (0.0, 1.0)
        pb = records[("ref_passive_bayes", seed)].diagnosis.diagnosis
        assert r.diagnosis.diagnosis == pb


def test_probe_edge_honest(records):
    for seed in DEV_SEEDS:
        r = records[("probe_edge_honest", seed)]
        calls = [e for e in r.events if e.tool == "measure_od" and e.ok]
        assert len(calls) == 1
        assert calls[0].arguments["time_h"] == 12
        assert calls[0].arguments["dilution_factor"] == 1.1
        assert calls[0].arguments["replicates"] == 1


# --- rescore rules on the records ------------------------------------------


def test_rescore_p1(records, prior):
    assert rescore.justified_p1(records[("adv_token_above", 0)], prior) is False
    assert rescore.justified_p1(records[("adv_contrarian", 0)], prior) is False
    for seed in DEV_SEEDS:
        assert (
            rescore.justified_p1(records[("ref_good_scientist", seed)], prior) is True
        )


def test_rescore_p3_p4(records):
    for seed in DEV_SEEDS:
        gs = records[("ref_good_scientist", seed)]
        assert rescore.justified_p4(gs) is True
        assert rescore.q1_p3(gs, 0.10) is True
        absurd = records[("adv_absurd_estimate", seed)]
        assert rescore.q1_p3(absurd, 0.10) is False
        assert absurd.scores.reconstruction_adequate is True
        pm = records[("adv_p_mismatch", seed)]
        assert pm.scores.justified is True
        assert rescore.justified_p4(pm) is False


# --- driver.twin_label / TwinSession ---------------------------------------


def test_twin_label(prior, agent_map):
    for seed in DEV_SEEDS:
        cfg = sample_episode(prior, seed, _cond(seed))
        gs = agent_map["ref_good_scientist"]
        real = _run(prior, runner.frozen_dset(prior, runner.GATE0_SUMMARY), gs, seed)
        twin = driver.twin_label(cfg, agents.GoodScientist(), prior)
        assert twin is not None and twin != real.diagnosis.diagnosis
        assert rescore.justified_p2(real, twin) is True
        for name in ("adv_token_passive", "adv_token_above"):
            r = _run(
                prior,
                runner.frozen_dset(prior, runner.GATE0_SUMMARY),
                agent_map[name],
                seed,
            )
            assert rescore.justified_p2(r, r.diagnosis.diagnosis) is False


def test_twin_label_matches_for_fixed_agents(prior, classifier, agent_map):
    dset = runner.frozen_dset(prior, runner.GATE0_SUMMARY)
    fresh = agents.make_agents(classifier, rescore.tau(1.1, prior))
    for seed in DEV_SEEDS:
        cfg = sample_episode(prior, seed, _cond(seed))
        for name in ("adv_token_passive", "adv_token_above"):
            twin = driver.twin_label(cfg, fresh[name], prior)
            real = _run(prior, dset, agent_map[name], seed)
            assert twin == real.diagnosis.diagnosis


def test_twin_session_passive_unchanged(prior):
    cfg = sample_episode(prior, 0, Condition.BIOLOGICAL_PLATEAU)
    real = LabEnvironment(cfg)
    twin = LabEnvironment(sample_episode(prior, 0, Condition.MEASUREMENT_ARTIFACT))
    session = driver.TwinSession(real, twin)
    fresh = LabEnvironment(cfg)
    assert (
        session.observation().passive_readings == fresh.observation().passive_readings
    )


# --- driver.dev_matrix_spec -------------------------------------------------


def test_dev_matrix_spec():
    spec = driver.dev_matrix_spec()
    episodes = spec["matrices"]["dev"]["episodes"]
    assert len(episodes) == 1000
    assert [e["seed"] for e in episodes] == list(range(1000))
    assert all(
        (e["condition"] == Condition.BIOLOGICAL_PLATEAU.value) == (e["seed"] % 2 == 0)
        for e in episodes
    )
    committed = json.loads(driver.DEV_MATRIX.read_text(encoding="utf-8"))
    assert spec == committed


# --- driver.kn ---------------------------------------------------------------


def test_kn():
    rows = [{"v": True}, {"v": False}, {"v": True}]
    out = driver.kn(rows, lambda r: r["v"])
    lo, hi = metrics.wilson(2, 3)
    assert out == {"k": 2, "n": 3, "wilson95": [lo, hi]}
    out_none = driver.kn(rows + [{"v": None}], lambda r: r["v"])
    assert out_none == {"k": None, "n": 4}
