"""Action-surface acceptance test for BinderBioPOMDP."""

import pytest

from mirage.core import ActionType
from mirage.environments.binder import BinderBioPOMDP, BinderWorldMode


@pytest.mark.parametrize("kind", list(ActionType))
def test_every_canonical_action_is_executable_from_a_fresh_world(kind: ActionType) -> None:
    env = BinderBioPOMDP(BinderWorldMode.MIXED)
    env.reset(11)
    action = next(item for item in env.available_actions() if item.action_type == kind)
    result = env.step(action)
    assert result.action == action
