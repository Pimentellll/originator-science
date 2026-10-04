"""Aggregation, paired-seed enforcement, privileged store separation."""

import json

import pytest

from campaign_support import SyntheticOracle, TraceBuilder, confident, make_belief
from mirage.core import ActionType as A
from mirage.evaluation.campaign import (
    CampaignEvaluator,
    EvaluationStore,
    FailureLabels,
    PairingError,
    build_benchmark_summary,
    paired_comparison,
)
from mirage.evaluation.campaign.aggregate import wilson
from mirage.provenance import find_privileged_fields

EV = CampaignEvaluator()
GOOD = FailureLabels()


def episode(policy, seed, *, justified, scenario="SINGLE_FAILURE"):
    b = TraceBuilder(episode_id=f"{policy}-{seed}", seed=seed, policy=policy)
    belief = confident()
    if justified:
        for a in (A.MEASURE_STABILITY, A.MEASURE_SEC, A.MEASURE_SPR, A.MEASURE_EPITOPE, A.MEASURE_DEVELOPABILITY):
            b.measure(a, belief_before=belief, belief_after=belief)
        b.measure(A.VALIDATE_ASSAY, {"control_signal": 0.9}, belief_before=belief, belief_after=belief)
    b.decide(A.SELECT, belief)
    return EV.evaluate(b.build(), SyntheticOracle(GOOD, scenario=scenario))


def test_wilson_bounds():
    r = wilson(5, 10)
    assert r.rate == 0.5 and 0.2 < r.lo < 0.5 < r.hi < 0.8
    assert wilson(0, 0).rate is None
    assert wilson(10, 10).hi == 1.0


def test_summary_separates_correct_from_justified():
    evals = [episode("p", s, justified=(s % 2 == 0)) for s in range(10)]
    summary = build_benchmark_summary("bm", evals)
    g = summary.policies["p"].overall
    assert g.correct.k == 10 and g.justified.k == 5 and g.lucky_correct.k == 5
    assert g.exploitation_flag_counts["lucky_correct"] == 5
    assert summary.seeds == tuple(range(10))


def test_summary_reports_by_scenario_class_separately():
    evals = [episode("p", 0, justified=True, scenario="SINGLE_FAILURE"),
             episode("p", 1, justified=False, scenario="ASSAY_FAILURE")]
    by = build_benchmark_summary("bm", evals).policies["p"].by_scenario_class
    assert set(by) == {"SINGLE_FAILURE", "ASSAY_FAILURE"}
    assert by["SINGLE_FAILURE"].justified.k == 1 and by["ASSAY_FAILURE"].justified.k == 0


def test_identical_seed_enforcement():
    ok = [episode(p, s, justified=True) for p in ("a", "b") for s in range(3)]
    assert build_benchmark_summary("bm", ok).seeds == (0, 1, 2)
    different = ok[:-1] + [episode("b", 99, justified=True)]
    with pytest.raises(PairingError):
        build_benchmark_summary("bm", different)
    with pytest.raises(PairingError):
        paired_comparison(different, "a", "b")
    dup = ok + [episode("a", 0, justified=True)]
    with pytest.raises(PairingError):
        build_benchmark_summary("bm", dup)
    clash = [episode("a", 0, justified=True, scenario="X"), episode("b", 0, justified=True, scenario="Y")]
    with pytest.raises(PairingError):
        build_benchmark_summary("bm", clash)


def test_paired_comparison_counts():
    evals = []
    for s in range(6):
        evals.append(episode("a", s, justified=s < 4))   # a justified on 0-3
        evals.append(episode("b", s, justified=s in (2, 3, 4)))  # b on 2-4
    c = paired_comparison(evals, "a", "b")
    assert (c.both_justified, c.justified_a_only, c.justified_b_only, c.neither_justified) == (2, 2, 1, 1)
    assert c.n_seeds == 6


def test_mixed_evaluator_versions_rejected():
    e = episode("p", 0, justified=True)
    other = e.model_copy(update={"evaluator_version": "campaign-eval/2", "seed": 1})
    with pytest.raises(ValueError):
        build_benchmark_summary("bm", [e, other], require_paired=False)


def test_store_roundtrip_and_summary_has_no_truth(tmp_path):
    store = EvaluationStore(tmp_path / "privileged")
    evals = [episode(p, s, justified=True) for p in ("a", "b") for s in range(2)]
    for e in evals:
        store.save_evaluation(e)
    assert store.load_evaluation("a-0") == evals[0]
    summary = build_benchmark_summary("bm-1", evals)
    store.save_summary(summary)
    assert store.load_summary("bm-1") == summary and store.list_summaries() == ["bm-1"]
    raw = json.dumps(summary.model_dump(mode="json"))
    for needle in ("episode_id", "decision_candidate_id", "public_digest", "failure_labels"):
        assert needle not in raw
    with pytest.raises(ValueError):
        store.load_summary("../escape")
    with pytest.raises(FileNotFoundError):
        store.load_summary("nope")
