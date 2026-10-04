"""PPOPolicy honours the common ScientificPolicy contract (gate G8)."""

import numpy as np
import pytest

pytest.importorskip("gymnasium")
sb3 = pytest.importorskip("sb3_contrib")

from stable_baselines3.common.vec_env import DummyVecEnv

from mirage.policies.base import PolicyError, ScientificPolicy
from mirage.rl.evaluate import rollout_policy, summarise
from mirage.rl.gym_env import BinderCampaignEnv
from mirage.rl.observation import ACTION_INDEX
from mirage.rl.policy import PPOPolicy
from mirage.rl.randomization import TRAIN_SEEDS


@pytest.fixture(scope="module")
def checkpoint(tmp_path_factory):
    vec = DummyVecEnv([lambda: BinderCampaignEnv(TRAIN_SEEDS, particles=32)])
    model = sb3.MaskablePPO("MlpPolicy", vec, n_steps=64, batch_size=32, seed=0, device="cpu")
    model.learn(64)
    path = tmp_path_factory.mktemp("ckpt") / "tiny"
    model.save(path)
    return path


def test_is_a_scientific_policy_and_only_returns_available_actions(checkpoint):
    policy = PPOPolicy(checkpoint)
    assert isinstance(policy, ScientificPolicy)
    env = BinderCampaignEnv([5, 6, 7], sequential=True, particles=32)
    for _ in range(3):
        env.reset()
        done = False
        while not done:
            action = policy.choose_action(env.public_state, env.public_summary, env.public_available)
            assert action in env.public_available
            _, _, done, _, _ = env.step(ACTION_INDEX[action.action_type])


def test_deterministic_and_stateless(checkpoint):
    policy = PPOPolicy(checkpoint)
    first = rollout_policy(policy, [101, 102], randomize=False, particles=32)
    second = rollout_policy(PPOPolicy(checkpoint), [101, 102], randomize=False, particles=32)
    assert first == second


def test_terminal_state_raises(checkpoint):
    policy = PPOPolicy(checkpoint)
    env = BinderCampaignEnv([9], particles=32)
    env.reset()
    env.step(11)  # first decisive action in canonical order: SELECT index 10 / REJECT 11
    with pytest.raises(PolicyError):
        policy.choose_action(env.public_state, env.public_summary, env.public_available)


def test_summaries_report_training_utility_not_scientific_claims(checkpoint):
    s = summarise(rollout_policy(PPOPolicy(checkpoint), [1, 2, 3], randomize=True, particles=32))
    assert {"return_mean", "terminal_rate", "action_distribution", "by_world_mode"} <= set(s)
