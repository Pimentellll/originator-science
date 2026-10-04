"""Tests for the public/private firewall in core environment contracts."""

import json
import math

import pytest
from pydantic import ValidationError

from mirage.core import (
    ActionType,
    AgentState,
    Candidate,
    ResourceState,
    ScientificAction,
    ScientificObservation,
    StepResult,
)


def public_state() -> AgentState:
    candidate = Candidate(candidate_id="binder-001", generation=0)
    return AgentState(
        active_candidate=candidate,
        candidates=(candidate,),
        resources=ResourceState(
            budget_remaining=12.0,
            sample_remaining=4.0,
            simulated_time=0.0,
            spr_instrument_health=1.0,
        ),
        observations=(
            ScientificObservation(
                action_type=ActionType.MEASURE_SPR,
                candidate_id=candidate.candidate_id,
                measurements={"log_kd": -8.4, "log_koff": -2.2},
                quality="nominal",
                notes=("Two public assay estimates were returned.",),
            ),
        ),
    )


def test_structured_observation_supports_multiple_measurements() -> None:
    observation = public_state().observations[0]
    assert observation.measurements == {"log_kd": -8.4, "log_koff": -2.2}
    assert observation.notes == ("Two public assay estimates were returned.",)
    assert "value" not in observation.model_dump()
    assert "uncertainty" not in observation.model_dump()


def test_public_state_serializes_without_hidden_binder_variables() -> None:
    payload = json.dumps(public_state().model_dump(mode="json"), sort_keys=True)
    forbidden = (
        "hidden",
        "truth",
        "simulator",
        "privileged",
        "true_log_kd",
        "true_log_koff",
        "assay_validity",
        "model_validity",
        "developability_liability",
    )
    assert not any(name in payload.lower() for name in forbidden)
    assert json.loads(payload)["observations"][0]["measurements"]["log_kd"] == -8.4


def test_public_models_reject_undeclared_fields_and_nonfinite_measurements() -> None:
    with pytest.raises(ValidationError):
        Candidate(
            candidate_id="binder-001",
            generation=0,
            true_log_kd=-9.1,
        )
    with pytest.raises(ValidationError):
        ScientificObservation(
            action_type=ActionType.MEASURE_SPR,
            candidate_id="binder-001",
            measurements={"log_kd": math.nan},
            quality="nominal",
        )
    with pytest.raises(ValidationError):
        ScientificObservation(
            action_type=ActionType.MEASURE_SEC,
            candidate_id="binder-001",
            measurements={"monomer_fraction": 0.9},
            quality="nominal",
            metadata={"true_log_kd": -9.1},
        )


def test_public_models_are_frozen() -> None:
    state = public_state()
    with pytest.raises(ValidationError):
        state.resources.budget_remaining = 0  # type: ignore[misc]


def test_step_result_remains_publicly_serializable() -> None:
    state = public_state()
    action = ScientificAction(
        action_type=ActionType.MEASURE_SPR,
        candidate_id="binder-001",
    )
    result = StepResult(action=action, observation=state.observations[0], state=state, terminal=False)
    payload = json.loads(result.model_dump_json())
    assert payload["action"]["action_type"] == "MEASURE_SPR"
    assert payload["observation"]["measurements"] == {"log_kd": -8.4, "log_koff": -2.2}


def test_action_types_are_exactly_the_canonical_binder_actions() -> None:
    assert {action.value for action in ActionType} == {
        "MEASURE_STABILITY",
        "MEASURE_SEC",
        "MEASURE_SPR",
        "MEASURE_EPITOPE",
        "MEASURE_DEVELOPABILITY",
        "VALIDATE_ASSAY",
        "ORTHOGONAL_FUNCTION",
        "REDESIGN_STABILITY",
        "REDESIGN_SOLUBILITY",
        "REDESIGN_INTERFACE",
        "SELECT",
        "REJECT",
        "MODEL_INVALID",
        "ABSTAIN",
    }
