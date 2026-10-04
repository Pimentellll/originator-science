"""Campaign path-dependence and resource-boundary tests."""

import pytest

from mirage.core import ActionType
from mirage.environments.binder import BinderBioPOMDP, BinderWorldMode


def available(env: BinderBioPOMDP, kind: ActionType):
    return next(item for item in env.available_actions() if item.action_type == kind)


def test_resource_exhaustion_removes_experiments_but_retains_terminal_choices() -> None:
    env = BinderBioPOMDP(BinderWorldMode.SINGLE_FAILURE)
    env.reset(2)
    for _ in range(12):
        env.step(available(env, ActionType.MEASURE_STABILITY))
    assert env.agent_state().resources.budget_remaining == 0.0
    kinds = {item.action_type for item in env.available_actions()}
    assert kinds == {ActionType.SELECT, ActionType.REJECT, ActionType.MODEL_INVALID, ActionType.ABSTAIN}


def test_unavailable_experiment_is_rejected_without_state_transition() -> None:
    env = BinderBioPOMDP(BinderWorldMode.SINGLE_FAILURE)
    env.reset(2)
    for _ in range(12):
        env.step(available(env, ActionType.MEASURE_STABILITY))
    before = env.agent_state()
    with pytest.raises(ValueError, match="unavailable"):
        env.step(available(BinderBioPOMDP(), ActionType.MEASURE_STABILITY))
    assert env.agent_state() == before


def test_spr_first_changes_the_later_public_campaign_state() -> None:
    env = BinderBioPOMDP(BinderWorldMode.COMPOUND_FAILURE)
    env.reset(9)
    first = env.step(available(env, ActionType.MEASURE_SPR))
    assert first.state.resources.spr_instrument_health < 1.0
    assert first.observation is not None and first.observation.quality == "degraded"
    env.step(available(env, ActionType.MEASURE_SEC))
    later = env.step(available(env, ActionType.MEASURE_SPR))
    assert later.state.resources.spr_instrument_health < first.state.resources.spr_instrument_health
    assert later.observation is not None and later.observation.quality == "degraded"
