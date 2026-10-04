"""C1: the executable reward-hacking specification."""

import pytest

from mirage.evaluation.campaign import CampaignEvaluator
from mirage.evaluation.campaign.adversarial import SPEC_CASES, run_spec_cases


@pytest.mark.parametrize("result", run_spec_cases(), ids=lambda r: r.case)
def test_spec_case(result):
    assert result.passed, result.problems


def test_suite_covers_the_documented_threats():
    names = {c.name for c in SPEC_CASES}
    required = {
        "misleading_proxy_bad_molecule", "broken_assay_blind_select", "model_invalid_done_right",
        "compound_collapsed_to_single_cause", "premature_aggregated_spr", "appropriate_abstention",
        "self_confirming_terminal_claim", "redesign_on_assay_artefact", "lucky_model_invalid",
    }
    assert required <= names and len(SPEC_CASES) >= 15


def test_every_case_trace_is_public_and_valid():
    from mirage.provenance import find_privileged_fields, validate_record

    for case in SPEC_CASES:
        record, _ = case.build()
        assert validate_record(record) == [], case.name
        assert find_privileged_fields(record.model_dump(mode="json")) == [], case.name


def test_suite_is_deterministic():
    a = [r.evaluation.model_dump_json() for r in run_spec_cases(CampaignEvaluator())]
    b = [r.evaluation.model_dump_json() for r in run_spec_cases(CampaignEvaluator())]
    assert a == b
