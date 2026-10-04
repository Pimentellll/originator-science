"""D0a: the public ScientificEvent / EpisodeRecord model and its validation."""

import json

import pytest
from pydantic import ValidationError

from campaign_support import TraceBuilder, confident, make_belief
from mirage.core import ActionType, ResourceState, ScientificAction
from mirage.provenance import (
    EpisodeRecord,
    ProvenanceError,
    ScientificEvent,
    assert_valid_record,
    find_privileged_fields,
    validate_belief_payload,
    validate_record,
)


def full_trace() -> EpisodeRecord:
    b = TraceBuilder()
    b.measure(ActionType.MEASURE_SEC, {"monomer_fraction": 0.9}, belief_before=make_belief(), belief_after=confident())
    b.measure(ActionType.MEASURE_SPR, {"log_kd": -8.0, "log_koff": -3.5}, belief_before=confident(), belief_after=confident())
    b.redesign(ActionType.REDESIGN_STABILITY, belief_before=confident(), belief_after=make_belief())
    b.decide(ActionType.REJECT, confident(p_folding_failure=0.9))
    return b.build()


def codes(record):
    return {i.code for i in validate_record(record)}


def test_valid_record_has_no_issues():
    record = full_trace()
    assert validate_record(record) == []
    assert_valid_record(record)
    assert record.is_terminal


def test_event_is_immutable_and_strict():
    event = full_trace().events[0]
    with pytest.raises(ValidationError):
        event.step = 5
    with pytest.raises(ValidationError):
        ScientificEvent(**{**event.model_dump(), "hidden_truth": 1.0})


def test_event_field_set_matches_d0():
    fields = set(ScientificEvent.model_fields)
    required = {
        "episode_id", "step", "candidate_id", "action", "observation", "belief_before",
        "belief_after", "resources_before", "resources_after", "policy_name", "rationale",
    }
    assert required <= fields
    assert fields - required == {"child_candidate_id"}


def test_redesign_requires_child_id_and_only_redesign():
    event = full_trace().events[2]
    assert event.child_candidate_id == "cand-0-r1"
    with pytest.raises(ValidationError):
        ScientificEvent(**{**event.model_dump(), "child_candidate_id": None})
    measure = full_trace().events[0]
    with pytest.raises(ValidationError):
        ScientificEvent(**{**measure.model_dump(), "child_candidate_id": "x"})


def test_observation_must_match_action():
    event = full_trace().events[0].model_dump()
    event["observation"]["action_type"] = ActionType.MEASURE_SPR
    with pytest.raises(ValidationError):
        ScientificEvent(**event)


def test_noncontiguous_steps_detected():
    record = full_trace()
    events = list(record.events)
    events[1] = ScientificEvent(**{**events[1].model_dump(), "step": 7})
    assert "non_contiguous_step" in codes(record.model_copy(update={"events": tuple(events)}))


def test_resource_discontinuity_and_increase_detected():
    record = full_trace()
    events = list(record.events)
    bad = events[1].model_dump()
    bad["resources_before"] = ResourceState(
        budget_remaining=999, sample_remaining=1, simulated_time=0, spr_instrument_health=1
    ).model_dump()
    events[1] = ScientificEvent(**bad)
    found = codes(record.model_copy(update={"events": tuple(events)}))
    assert {"resource_discontinuity", "resource_increase"} <= found


def test_uncharged_measurement_detected():
    b = TraceBuilder()
    event = b.measure(ActionType.MEASURE_SEC)
    free = ScientificEvent(**{**event.model_dump(), "resources_after": event.resources_before.model_dump()})
    record = b.build().model_copy(update={"events": (free,)})
    assert "uncharged_action" in codes(record)


def test_wrong_measurement_names_detected():
    b = TraceBuilder()
    event = b.measure(ActionType.MEASURE_SEC)
    data = event.model_dump()
    data["observation"]["measurements"] = {"log_kd": -7.0}
    record = b.build().model_copy(update={"events": (ScientificEvent(**data),)})
    assert "measurement_schema" in codes(record)


def test_event_after_terminal_and_terminal_resources():
    b = TraceBuilder()
    b.decide(ActionType.ABSTAIN, make_belief())
    record = b.build()
    extra = ScientificEvent(**{**record.events[0].model_dump(), "step": 1})
    assert "event_after_terminal" in codes(record.model_copy(update={"events": (record.events[0], extra)}))


def test_terminal_decision_must_match_last_event():
    record = full_trace()
    wrong = record.model_copy(update={"terminal_decision": ScientificAction(action_type=ActionType.SELECT, candidate_id="cand-0-r1")})
    assert "terminal_mismatch" in codes(wrong)
    unrecorded = record.model_copy(update={"terminal_decision": None})
    assert "terminal_not_recorded" in codes(unrecorded)


def test_unknown_candidate_and_duplicate_child_detected():
    record = full_trace()
    events = list(record.events)
    events[1] = ScientificEvent(**{**events[1].model_dump(), "candidate_id": "ghost",
                                    "action": ScientificAction(action_type=ActionType.MEASURE_SPR, candidate_id="ghost").model_dump(),
                                    "observation": {**events[1].observation.model_dump(), "candidate_id": "ghost"}})
    assert "unknown_candidate" in codes(record.model_copy(update={"events": tuple(events)}))


def test_belief_payload_validation():
    validate_belief_payload(make_belief())
    for bad in (
        {k: v for k, v in make_belief().items() if k != "p_assay_invalid"},
        make_belief(p_folding_failure=1.5),
        make_belief(particles=[1, 2]),
        make_belief(continuous_variances={"x": -1.0}),
        make_belief(posterior_entropy=-1.0),
    ):
        with pytest.raises(ValueError):
            validate_belief_payload(bad)


def test_event_rejects_invalid_belief():
    event = full_trace().events[0].model_dump()
    event["belief_after"] = make_belief(p_model_invalid=2.0)
    with pytest.raises(ValidationError):
        ScientificEvent(**event)


def test_digest_is_stable_and_sensitive():
    a, b = full_trace(), full_trace()
    assert a.digest() == b.digest()
    changed = a.model_copy(update={"seed": 99})
    assert changed.digest() != a.digest()


def test_privileged_key_in_record_is_flagged():
    record = full_trace()
    assert find_privileged_fields(record.model_dump(mode="json")) == []
    assert find_privileged_fields({"a": [{"_simulator_truth": 1}]}) == ["a[0]._simulator_truth"]
    assert find_privileged_fields({"particles": []})
    assert find_privileged_fields({"p_assay_invalid": 0.2, "log_kd": -7, "log_koff": -3}) == []


def test_policy_config_rejects_privileged_keys():
    from mirage.provenance import PolicyMetadata

    PolicyMetadata(name="p", config={"threshold": 0.5})
    with pytest.raises(ValidationError):
        PolicyMetadata(name="p", config={"_privileged_state": 1})


def test_assert_valid_record_raises_with_issues():
    record = full_trace().model_copy(update={"terminal_decision": None})
    with pytest.raises(ProvenanceError):
        assert_valid_record(record)


def test_canonical_json_roundtrip():
    record = full_trace()
    again = EpisodeRecord.model_validate_json(record.model_dump_json())
    assert again == record and again.digest() == record.digest()
    json.loads(record.canonical_json())
