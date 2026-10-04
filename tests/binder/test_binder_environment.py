"""Executable acceptance tests for the Binder environment facade."""

import json

import pytest

from mirage.core import ActionType, ScientificAction
from mirage.environments.binder import BinderBioPOMDP, BinderWorldMode, SHOWCASE_SCENARIOS


def trace(env: BinderBioPOMDP) -> list[dict]:
    env.reset(73)
    results = []
    for kind in (ActionType.MEASURE_SEC, ActionType.MEASURE_SPR, ActionType.REDESIGN_SOLUBILITY, ActionType.MEASURE_STABILITY):
        action = next(item for item in env.available_actions() if item.action_type == kind)
        results.append(env.step(action).model_dump(mode="json"))
    return results


def test_reset_and_action_sequence_are_seeded() -> None:
    assert trace(BinderBioPOMDP(BinderWorldMode.COMPOUND_FAILURE)) == trace(BinderBioPOMDP(BinderWorldMode.COMPOUND_FAILURE))


def test_public_state_has_no_world_mode_or_hidden_truth() -> None:
    payload = json.dumps(BinderBioPOMDP(BinderWorldMode.MIXED).reset(4).model_dump(mode="json")).lower()
    for forbidden in ("mixed", "hidden", "truth", "assay_valid", "model_valid", "developability_liability"):
        assert forbidden not in payload


def test_measurement_transitions_public_resources() -> None:
    env = BinderBioPOMDP(BinderWorldMode.SINGLE_FAILURE)
    before = env.reset(1).resources
    result = env.step(next(item for item in env.available_actions() if item.action_type == ActionType.MEASURE_STABILITY))
    assert result.observation is not None
    assert result.state.resources.budget_remaining == before.budget_remaining - 1.0
    assert result.state.resources.sample_remaining == before.sample_remaining - 0.5
    assert result.state.resources.simulated_time == before.simulated_time + 0.5


def test_aggregated_spr_degrades_future_instrument_health() -> None:
    env = BinderBioPOMDP(BinderWorldMode.COMPOUND_FAILURE)
    env.reset(9)
    first = env.step(next(item for item in env.available_actions() if item.action_type == ActionType.MEASURE_SPR))
    second = env.step(next(item for item in env.available_actions() if item.action_type == ActionType.MEASURE_SPR))
    assert first.observation is not None and first.observation.quality == "degraded"
    assert second.state.resources.spr_instrument_health < first.state.resources.spr_instrument_health < 1.0


def test_redesign_creates_public_lineage() -> None:
    env = BinderBioPOMDP()
    env.reset(5)
    result = env.step(next(item for item in env.available_actions() if item.action_type == ActionType.REDESIGN_STABILITY))
    assert result.observation is None
    assert result.state.active_candidate.generation == 1
    assert result.state.active_candidate.parent_candidate_id == "binder-000"
    assert len(result.state.candidates) == 2


def test_terminal_actions_end_episode() -> None:
    env = BinderBioPOMDP()
    env.reset(5)
    result = env.step(next(item for item in env.available_actions() if item.action_type == ActionType.ABSTAIN))
    assert result.terminal is True and env.available_actions() == ()
    with pytest.raises(ValueError, match="terminal"):
        env.step(ScientificAction(action_type=ActionType.SELECT, candidate_id="binder-000"))


def test_five_canonical_showcases_cover_all_world_modes() -> None:
    assert [item.name for item in SHOWCASE_SCENARIOS] == ["instability", "aggregation_kinetic_defect", "broken_assay", "invalid_biological_model", "misleading_proxy_trap"]
    assert {item.world_mode for item in SHOWCASE_SCENARIOS} == set(BinderWorldMode)
    assert all(BinderBioPOMDP.from_showcase(item.name).reset(3).active_candidate.candidate_id == "binder-000" for item in SHOWCASE_SCENARIOS)
