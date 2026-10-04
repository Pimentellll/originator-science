"""Tests for the public/private firewall in core environment contracts."""

import json

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
                action_type=ActionType.MEASURE_STABILITY,
                candidate_id=candidate.candidate_id,
                value=0.72,
                uncertainty=0.08,
                unit="fraction",
                quality="nominal",
            ),
        ),
    )


def test_public_state_serializes_without_hidden_binder_variables() -> None:
    payload = json.dumps(public_state().model_dump(mode="json"), sort_keys=True)
    forbidden = (
        "hidden",
        "truth",
        "log_kd",
        "koff",
        "epitope_state",
        "assay_validity",
        "model_validity",
        "monomer_fraction",
        "developability_liability",
    )
    assert not any(name in payload.lower() for name in forbidden)


def test_public_models_reject_undeclared_fields() -> None:
    with pytest.raises(ValidationError):
        Candidate(
            candidate_id="binder-001",
            generation=0,
            true_log_kd=-9.1,
        )


def test_public_models_are_frozen() -> None:
    state = public_state()
    with pytest.raises(ValidationError):
        state.resources.budget_remaining = 0  # type: ignore[misc]


def test_step_result_remains_publicly_serializable() -> None:
    state = public_state()
    action = ScientificAction(
        action_type=ActionType.MEASURE_STABILITY,
        candidate_id="binder-001",
    )
    result = StepResult(action=action, observation=state.observations[0], state=state, terminal=False)
    assert json.loads(result.model_dump_json())["action"]["action_type"] == "MEASURE_STABILITY"


def test_action_types_include_the_provisional_binder_mvp() -> None:
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
