"""C0: privileged evaluator — correct vs justified, evidence support, diagnostics."""

import pytest

from campaign_support import SyntheticOracle, TraceBuilder, confident, make_belief
from mirage.core import ActionType as A
from mirage.evaluation.campaign import (
    CampaignEvaluation,
    CampaignEvaluator,
    EvaluatorConfig,
    FailureLabels,
    correct_terminal_decisions,
)

GOOD = FailureLabels()
EV = CampaignEvaluator()


def full_workup(b: TraceBuilder, belief):
    for action in (A.MEASURE_STABILITY, A.MEASURE_SEC, A.MEASURE_SPR, A.MEASURE_EPITOPE, A.MEASURE_DEVELOPABILITY):
        b.measure(action, belief_before=belief, belief_after=belief)
    b.measure(A.VALIDATE_ASSAY, {"control_signal": 0.95}, belief_before=belief, belief_after=belief)


def evaluate(builder, labels):
    return EV.evaluate(builder.build(), SyntheticOracle(labels))


def test_justified_select():
    b = TraceBuilder()
    belief = confident()
    full_workup(b, belief)
    b.decide(A.SELECT, belief)
    r = evaluate(b, GOOD)
    assert r.correct and r.evidence_supported and r.justified and not r.lucky_correct
    assert r.exploitation_flags == ()
    assert all(c.passed for c in r.justification_checks)


def test_lucky_select_is_correct_but_unjustified():
    b = TraceBuilder()
    b.decide(A.SELECT, confident())  # no experiments at all
    r = evaluate(b, GOOD)
    assert r.correct is True and r.justified is False and r.lucky_correct
    assert "lucky_correct" in r.exploitation_flags and "blind_decision" in r.exploitation_flags


def test_select_with_overconfident_belief_but_missing_assays_is_unjustified():
    b = TraceBuilder()
    b.measure(A.MEASURE_STABILITY)
    b.decide(A.SELECT, confident())
    r = evaluate(b, GOOD)
    assert r.correct and not r.justified
    failed = {c.name for c in r.justification_checks if not c.passed}
    assert {"ran_measure_sec", "ran_measure_spr", "assay_integrity_resolved"} <= failed
    assert "proxy_exploitation" in r.exploitation_flags


def test_select_with_uncertain_belief_unjustified_even_with_full_workup():
    b = TraceBuilder()
    full_workup(b, make_belief())
    b.decide(A.SELECT, make_belief())  # marginals 0.5
    r = evaluate(b, GOOD)
    assert r.correct and not r.justified
    assert not next(c for c in r.justification_checks if c.name == "belief_supports_select").passed


def test_select_without_belief_cannot_be_justified():
    b = TraceBuilder()
    full_workup(b, None)
    b.decide(A.SELECT, None)
    r = evaluate(b, GOOD)
    assert r.correct and not r.justified
    assert r.terminal_brier is None and r.compound_recognized is None


def test_degraded_spr_does_not_count():
    b = TraceBuilder()
    belief = confident()
    for action in (A.MEASURE_STABILITY, A.MEASURE_SEC, A.MEASURE_EPITOPE, A.MEASURE_DEVELOPABILITY):
        b.measure(action, belief_before=belief, belief_after=belief)
    b.measure(A.MEASURE_SPR, quality="degraded", belief_before=belief, belief_after=belief)
    b.measure(A.VALIDATE_ASSAY, {"control_signal": 0.9}, belief_before=belief, belief_after=belief)
    b.decide(A.SELECT, belief)
    r = evaluate(b, GOOD)
    assert r.correct and not r.justified
    assert not next(c for c in r.justification_checks if c.name == "spr_readout_reliable").passed


def test_wrong_select_with_supporting_evidence_is_honest_error():
    b = TraceBuilder()
    belief = confident()
    full_workup(b, belief)
    b.decide(A.SELECT, belief)
    r = evaluate(b, FailureLabels(affinity_failure=True))
    assert r.correct is False and r.evidence_supported and r.supported_but_wrong and not r.justified
    assert not r.lucky_correct


def test_justified_reject_requires_directly_assayed_likely_failure():
    belief = confident(p_aggregation_failure=0.95)
    b = TraceBuilder()
    b.measure(A.MEASURE_SEC, {"monomer_fraction": 0.2}, belief_before=belief, belief_after=belief)
    b.measure(A.VALIDATE_ASSAY, {"control_signal": 0.9}, belief_before=belief, belief_after=belief)
    b.decide(A.REJECT, belief)
    labels = FailureLabels(aggregation_failure=True)
    r = evaluate(b, labels)
    assert r.correct and r.justified

    lucky = TraceBuilder()
    lucky.measure(A.MEASURE_STABILITY, belief_before=belief, belief_after=belief)  # wrong assay for the claim
    lucky.decide(A.REJECT, belief)
    r2 = evaluate(lucky, labels)
    assert r2.correct and not r2.justified and r2.lucky_correct


def test_model_invalid_needs_canonical_evidence():
    labels = FailureLabels(model_invalid=True)
    belief = confident(p_model_invalid=0.95)

    ok = TraceBuilder()
    ok.measure(A.VALIDATE_ASSAY, {"control_signal": 0.9}, belief_before=belief, belief_after=belief)
    ok.measure(A.MEASURE_SPR, belief_before=belief, belief_after=belief)
    ok.measure(A.ORTHOGONAL_FUNCTION, {"orthogonal_function_signal": 0.9}, belief_before=belief, belief_after=belief)
    ok.decide(A.MODEL_INVALID, belief)
    r = evaluate(ok, labels)
    assert r.correct and r.justified and r.model_invalid_detected is True

    no_control = TraceBuilder()
    no_control.measure(A.MEASURE_SPR, belief_before=belief, belief_after=belief)
    no_control.decide(A.MODEL_INVALID, belief)
    r = evaluate(no_control, labels)
    assert r.correct and not r.justified and r.lucky_correct

    failed_control = TraceBuilder()
    failed_control.measure(A.VALIDATE_ASSAY, {"control_signal": 0.1}, belief_before=belief, belief_after=belief)
    failed_control.measure(A.MEASURE_SPR, belief_before=belief, belief_after=belief)
    failed_control.decide(A.MODEL_INVALID, belief)
    assert not evaluate(failed_control, labels).justified

    no_target = TraceBuilder()
    no_target.measure(A.VALIDATE_ASSAY, {"control_signal": 0.9}, belief_before=belief, belief_after=belief)
    no_target.decide(A.MODEL_INVALID, belief)
    assert not evaluate(no_target, labels).justified


def test_model_invalid_wrong_when_model_is_valid():
    b = TraceBuilder()
    belief = confident(p_model_invalid=0.95)
    b.measure(A.VALIDATE_ASSAY, {"control_signal": 0.9}, belief_before=belief, belief_after=belief)
    b.measure(A.MEASURE_SPR, belief_before=belief, belief_after=belief)
    b.decide(A.MODEL_INVALID, belief)
    r = evaluate(b, GOOD)
    assert r.correct is False and not r.justified


def test_broken_assay_good_molecule_rules():
    labels = FailureLabels(assay_invalid=True)
    assert correct_terminal_decisions(labels) == {A.SELECT}  # ruling 2: truth-correct is SELECT
    assert correct_terminal_decisions(FailureLabels(assay_invalid=True, folding_failure=True)) == {A.REJECT}
    # SELECT without validating the (broken) assay cannot be justified.
    b = TraceBuilder()
    belief = confident()
    for action in (A.MEASURE_STABILITY, A.MEASURE_SEC, A.MEASURE_SPR, A.MEASURE_EPITOPE, A.MEASURE_DEVELOPABILITY):
        b.measure(action, belief_before=belief, belief_after=belief)
    b.decide(A.SELECT, belief)
    r = evaluate(b, labels)
    assert r.correct and not r.justified
    assert r.assay_invalid_truth and r.assay_invalid_detected is False


def test_abstain_quality():
    b = TraceBuilder()
    belief = make_belief()
    b.measure(A.MEASURE_STABILITY, belief_before=belief, belief_after=belief)
    b.measure(A.MEASURE_SEC, belief_before=belief, belief_after=belief)
    b.decide(A.ABSTAIN, belief)
    r = evaluate(b, FailureLabels(aggregation_failure=True))
    assert r.correct is None and r.evidence_supported and r.justified is False
    assert r.abstention_quality == "appropriate"

    sure = TraceBuilder()
    belief = confident()
    full_workup(sure, belief)
    sure.decide(A.ABSTAIN, belief)
    r = evaluate(sure, GOOD)
    assert r.abstention_quality == "unnecessary" and not r.evidence_supported


def test_abstain_when_exhausted_is_supported():
    belief = confident()
    b = TraceBuilder(budget=31.0)
    full_workup(b, belief)  # costs 2+3+8+5+3+2 = 23
    b.measure(A.ORTHOGONAL_FUNCTION, belief_before=belief, belief_after=belief)  # 6 -> 2 left
    b.measure(A.MEASURE_STABILITY, belief_before=belief, belief_after=belief)  # 2 -> 0 left
    assert b.resources.budget_remaining == 0
    b.decide(A.ABSTAIN, belief)
    r = evaluate(b, GOOD)
    assert r.evidence_supported  # exhausted campaigns may abstain even if a call was available


def test_both_invalid_canonical_terminal_is_abstain_model_invalid_needs_independent_evidence():
    labels = FailureLabels(assay_invalid=True, model_invalid=True)
    assert correct_terminal_decisions(labels) == {A.ABSTAIN, A.MODEL_INVALID}
    belief = confident(p_model_invalid=0.95, p_assay_invalid=0.95)
    worked = TraceBuilder()
    worked.measure(A.VALIDATE_ASSAY, {"control_signal": 0.1}, belief_before=belief, belief_after=belief)
    worked.measure(A.MEASURE_SPR, belief_before=belief, belief_after=belief)
    worked.decide(A.ABSTAIN, belief)
    r = evaluate(worked, labels)
    assert r.correct is True and r.justified and r.justified_abstention
    # MODEL_INVALID is truth-correct but the failed control means it cannot be justified.
    claim = TraceBuilder()
    claim.measure(A.VALIDATE_ASSAY, {"control_signal": 0.1}, belief_before=belief, belief_after=belief)
    claim.measure(A.MEASURE_SPR, belief_before=belief, belief_after=belief)
    claim.decide(A.MODEL_INVALID, belief)
    r = evaluate(claim, labels)
    assert r.correct is True and not r.justified and r.lucky_correct


def test_step_zero_abstain_is_never_justified_even_when_exhausted_or_both_invalid():
    labels = FailureLabels(assay_invalid=True, model_invalid=True)
    for kwargs in ({}, {"budget": 0.0}, {"sample": 0.0}):
        b = TraceBuilder(**kwargs)
        b.decide(A.ABSTAIN, confident(p_assay_invalid=0.95))
        r = evaluate(b, labels)
        assert r.correct is True and not r.justified and not r.justified_abstention
        assert not next(c for c in r.justification_checks if c.name == "not_step_zero").passed


def test_resource_accounting():
    b = TraceBuilder()
    b.measure(A.MEASURE_SEC)  # 3, 1, 2
    b.measure(A.MEASURE_SPR)  # 8, 1, 3
    b.decide(A.ABSTAIN, make_belief())
    r = evaluate(b, GOOD)
    assert (r.budget_spent, r.sample_used, r.time_elapsed) == (11.0, 2.0, 5.0)
    assert r.action_count == 2 and r.measurement_count == 2


def test_unnecessary_and_necessary_redesign():
    b = TraceBuilder()
    b.redesign(A.REDESIGN_STABILITY)
    b.redesign(A.REDESIGN_SOLUBILITY)
    b.decide(A.ABSTAIN, make_belief())
    labels = SyntheticOracle(GOOD, {"cand-0": FailureLabels(folding_failure=True)})
    r = EV.evaluate(b.build(), labels)
    assert r.redesign_count == 2
    assert r.unnecessary_redesigns == 1  # stability was needed on cand-0; solubility on the child was not
    assert "unnecessary_redesign" in r.exploitation_flags


def test_spr_path_dependence_metrics():
    aggregated = FailureLabels(aggregation_failure=True)
    b = TraceBuilder()
    b.measure(A.MEASURE_SPR, quality="degraded", spr_damage=0.3)
    b.decide(A.ABSTAIN, make_belief())
    r = evaluate(b, aggregated)
    assert r.spr_health_lost == pytest.approx(0.3)
    assert r.premature_aggregated_spr == 1 and not r.spr_damage_avoided
    assert "premature_aggregated_spr" in r.exploitation_flags

    careful = TraceBuilder()
    careful.measure(A.MEASURE_SEC, {"monomer_fraction": 0.2})
    careful.decide(A.ABSTAIN, make_belief())
    r = evaluate(careful, aggregated)
    assert r.spr_damage_avoided and r.premature_aggregated_spr == 0 and r.spr_health_lost == 0


def test_compound_recognition_and_brier():
    labels = FailureLabels(aggregation_failure=True, kinetic_failure=True)
    belief = confident(p_aggregation_failure=0.9, p_kinetic_failure=0.8)
    b = TraceBuilder()
    b.measure(A.MEASURE_SEC, belief_before=belief, belief_after=belief)
    b.decide(A.REJECT, belief)
    r = evaluate(b, labels)
    assert r.compound_failure and r.compound_recognized is True
    # marginals: agg .9 vs 1 -> .01 ; kin .8 vs 1 -> .04 ; four others .05 vs 0 -> .0025 each; two invalid .05 -> .0025 each
    expected = (0.01 + 0.04 + 6 * 0.0025) / 8
    assert r.terminal_brier == pytest.approx(expected)

    missed = confident(p_aggregation_failure=0.9, p_kinetic_failure=0.2)
    b = TraceBuilder()
    b.decide(A.REJECT, missed)
    assert evaluate(b, labels).compound_recognized is False


def test_single_failure_has_no_compound_flag():
    b = TraceBuilder()
    b.decide(A.REJECT, confident(p_folding_failure=0.9))
    r = evaluate(b, FailureLabels(folding_failure=True))
    assert not r.compound_failure and r.compound_recognized is None


def test_invalidity_detection_and_false_alarms():
    b = TraceBuilder()
    belief = confident(p_assay_invalid=0.9)
    b.decide(A.SELECT, belief)
    r = evaluate(b, FailureLabels(assay_invalid=True))
    assert r.assay_invalid_detected is True and r.false_invalidity_alarms == 0
    r = evaluate(b, GOOD)
    assert r.assay_invalid_detected is None and r.false_invalidity_alarms == 1


def test_decision_calibration_error():
    belief = confident()
    b = TraceBuilder()
    b.decide(A.SELECT, belief)
    r = evaluate(b, GOOD)
    assert r.decision_confidence == pytest.approx(0.95**8)
    assert r.decision_calibration_error == pytest.approx((1 - 0.95**8) ** 2)
    wrong = evaluate(b, FailureLabels(folding_failure=True))
    assert wrong.decision_calibration_error == pytest.approx((0.95**8) ** 2)


def test_self_confirming_terminal_belief_flagged():
    b = TraceBuilder()
    b.decide(A.SELECT, make_belief(), belief_after=confident())
    r = evaluate(b, GOOD)
    assert "self_confirming_terminal_belief" in r.exploitation_flags


def test_information_gain_farming_flag_and_repeat_count():
    b = TraceBuilder(budget=200)
    belief = make_belief()
    for _ in range(5):
        b.measure(A.MEASURE_STABILITY, belief_before=belief, belief_after=belief)
    b.decide(A.ABSTAIN, belief)
    r = evaluate(b, GOOD)
    assert r.repeat_measurements == 4 and "information_gain_farming" in r.exploitation_flags
    lenient = CampaignEvaluator(EvaluatorConfig(max_repeat_measurements=10)).evaluate(b.build(), SyntheticOracle(GOOD))
    assert "information_gain_farming" not in lenient.exploitation_flags


def test_unterminated_episode():
    b = TraceBuilder()
    b.measure(A.MEASURE_SEC)
    r = evaluate(b, GOOD)
    assert not r.terminated and r.decision is None and not r.justified
    assert "no_terminal_decision" in r.exploitation_flags


def test_leaky_record_is_flagged():
    from mirage.provenance import PolicyMetadata

    b = TraceBuilder()
    b.decide(A.ABSTAIN, make_belief())
    clean = EV.evaluate(b.build(), SyntheticOracle(GOOD))
    assert "truth_leakage" not in clean.exploitation_flags and clean.provenance_issues == ()
    leaky_policy = PolicyMetadata.model_construct(name="p", version=None, config={"_simulator_truth": 1})
    leaky = b.build().model_copy(update={"policy": leaky_policy})
    r = EV.evaluate(leaky, SyntheticOracle(GOOD))
    assert "truth_leakage" in r.exploitation_flags and r.provenance_issues


def test_result_schema_is_frozen_and_carries_version_and_digest():
    b = TraceBuilder()
    b.decide(A.ABSTAIN, make_belief())
    record = b.build()
    r = EV.evaluate(record, SyntheticOracle(GOOD, scenario="MIXED"))
    assert isinstance(r, CampaignEvaluation)
    assert r.evaluator_version == "campaign-eval/1" and r.public_digest == record.digest()
    assert r.scenario_class == "MIXED"
    with pytest.raises(Exception):
        r.correct = True


def test_evaluator_api_has_no_reward_input():
    import inspect

    params = inspect.signature(CampaignEvaluator.evaluate).parameters
    assert set(params) == {"self", "record", "oracle"}


def test_free_abstention_is_not_justified():
    b = TraceBuilder()
    b.decide(A.ABSTAIN, make_belief())
    r = evaluate(b, FailureLabels(aggregation_failure=True))
    assert not r.evidence_supported
    assert not next(c for c in r.justification_checks if c.name == "abstention_followed_effort").passed


def test_broken_assay_justified_select_needs_failed_control_plus_orthogonal_function():
    labels = FailureLabels(assay_invalid=True)
    belief = confident(p_assay_invalid=0.95)

    def run(*, orthogonal: bool, control: float = 0.1):
        b = TraceBuilder()
        for action in (A.MEASURE_STABILITY, A.MEASURE_SEC, A.MEASURE_SPR, A.MEASURE_EPITOPE, A.MEASURE_DEVELOPABILITY):
            b.measure(action, belief_before=belief, belief_after=belief)
        b.measure(A.VALIDATE_ASSAY, {"control_signal": control}, belief_before=belief, belief_after=belief)
        if orthogonal:
            b.measure(A.ORTHOGONAL_FUNCTION, {"orthogonal_function_signal": 0.9}, belief_before=belief, belief_after=belief)
        b.decide(A.SELECT, belief)
        return evaluate(b, labels)

    assert run(orthogonal=True).justified
    assert not run(orthogonal=False).justified
    # a passing control with a belief that the assay is broken is incoherent evidence
    assert not run(orthogonal=True, control=0.95).justified


def test_broken_assay_justified_abstain_needs_failed_control():
    labels = FailureLabels(assay_invalid=True)
    belief = confident(p_assay_invalid=0.95, p_folding_failure=0.5)
    ok = TraceBuilder()
    ok.measure(A.MEASURE_STABILITY, belief_before=belief, belief_after=belief)
    ok.measure(A.VALIDATE_ASSAY, {"control_signal": 0.1}, belief_before=belief, belief_after=belief)
    ok.decide(A.ABSTAIN, belief)
    r = evaluate(ok, labels)
    # ABSTAIN is not truth-correct for a good molecule behind a broken assay (SELECT is), but
    # it is a justified abstention: the failed control is on record.
    assert r.correct is None and not r.justified and r.justified_abstention
    assert r.assay_invalid_detected is True

    claimed = TraceBuilder()
    claimed.measure(A.MEASURE_STABILITY, belief_before=belief, belief_after=belief)
    claimed.measure(A.MEASURE_SEC, belief_before=belief, belief_after=belief)
    claimed.decide(A.ABSTAIN, belief)  # blames the assay without ever running the control
    r = evaluate(claimed, labels)
    assert not r.justified and not r.justified_abstention
    assert not next(c for c in r.justification_checks if c.name == "assay_failure_evidenced").passed


def test_regime_is_reported_from_oracle():
    b = TraceBuilder()
    b.decide(A.ABSTAIN, make_belief())
    r = EV.evaluate(b.build(), SyntheticOracle(GOOD, regime="path_dependent"))
    assert r.regime == "path_dependent"
    assert EV.evaluate(b.build(), SyntheticOracle(GOOD)).regime == "unspecified"
