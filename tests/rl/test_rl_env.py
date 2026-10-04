"""F0/F2: the gym wrapper wraps the real environment and exposes only public information."""

import json

import numpy as np
import pytest

gym = pytest.importorskip("gymnasium")

from mirage.core import ActionType, ScientificAction
from mirage.environments.binder import BinderBioPOMDP, BinderWorldMode
from mirage.rl.binder_env import RandomizedBinderPOMDP
from mirage.rl.gym_env import BinderCampaignEnv
from mirage.rl.observation import ACTION_ORDER, FEATURE_NAMES, MAX_STEPS, N_ACTIONS, OBS_DIM, action_mask, build_observation
from mirage.rl.randomization import (
    CURRICULUM, HELD_OUT_SEEDS, TRAIN_SEEDS, VAL_SEEDS, WorldConfig, sample_world_config,
)

FORBIDDEN = ("ground_truth", "simulator_truth", "hidden", "scenario", "world_mode", "true_", "failure_mode", "privileged", "_truth")


def test_action_space_is_the_canonical_fourteen_in_enum_order():
    assert N_ACTIONS == 14 and ACTION_ORDER == tuple(ActionType)
    assert BinderCampaignEnv().action_space.n == 14


def test_observation_features_are_public_only_and_dimensions_match():
    assert OBS_DIM == len(FEATURE_NAMES) == BinderCampaignEnv().observation_space.shape[0]
    assert not [n for n in FEATURE_NAMES if any(bad in n.lower() for bad in FORBIDDEN)]


def test_observation_is_finite_bounded_float32_and_world_mode_never_leaks():
    env = BinderCampaignEnv(seeds=range(500, 520), sequential=True)
    for _ in range(20):
        obs, info = env.reset()
        assert obs.dtype == np.float32 and obs.shape == (OBS_DIM,)
        assert np.all(np.isfinite(obs)) and np.all(np.abs(obs) <= 5.0)
        assert info == {}
        text = json.dumps(info) + json.dumps(env.observation_space.shape)
        assert not any(bad in text.lower() for bad in FORBIDDEN)


def test_mask_equals_available_actions_and_never_empty():
    env = BinderCampaignEnv(seeds=range(600, 610), sequential=True)
    rng = np.random.default_rng(0)
    for _ in range(10):
        env.reset()
        done = False
        while not done:
            mask = env.action_masks()
            legal = {a.action_type for a in env.env.available_actions()}
            assert {ACTION_ORDER[i] for i in np.flatnonzero(mask)} == legal
            assert mask.any()
            _, _, done, _, _ = env.step(int(rng.choice(np.flatnonzero(mask))))


def test_decisive_actions_are_always_legal_and_resources_mask_assays():
    env = BinderCampaignEnv(seeds=[7], randomize=False)
    env.reset()
    env.env._resources = env.env._resources.model_copy(update={"budget_remaining": 0.0})
    env._available = env.env.available_actions()
    mask = env.action_masks()
    assert mask[[ACTION_ORDER.index(a) for a in (ActionType.SELECT, ActionType.REJECT, ActionType.MODEL_INVALID, ActionType.ABSTAIN)]].all()
    assert not mask[: ACTION_ORDER.index(ActionType.SELECT)].any()


def test_illegal_action_is_penalised_and_terminates():
    env = BinderCampaignEnv(seeds=[7], randomize=False)
    env.reset()
    env.env._resources = env.env._resources.model_copy(update={"budget_remaining": 0.0})
    env._available = env.env.available_actions()
    _, reward, terminated, _, info = env.step(ACTION_ORDER.index(ActionType.MEASURE_SPR))
    assert terminated and reward == env.reward_cfg.illegal_penalty and info["episode_summary"]["illegal"]


def test_same_seed_and_actions_reproduce_observations_and_rewards():
    def rollout():
        env = BinderCampaignEnv(seeds=[4242])
        obs, _ = env.reset()
        trace = [obs.copy()]
        for a in (ActionType.MEASURE_SEC, ActionType.MEASURE_SPR, ActionType.VALIDATE_ASSAY, ActionType.REDESIGN_SOLUBILITY, ActionType.MEASURE_SEC, ActionType.REJECT):
            obs, r, done, _, _ = env.step(ACTION_ORDER.index(a))
            trace.append((obs.copy(), r))
            if done:
                break
        return trace

    first, second = rollout(), rollout()
    assert np.array_equal(first[0], second[0])
    for (o1, r1), (o2, r2) in zip(first[1:], second[1:]):
        assert np.array_equal(o1, o2) and r1 == r2


def test_nominal_randomized_env_is_identical_to_the_real_environment():
    for mode in BinderWorldMode:
        real, wrapped = BinderBioPOMDP(mode), RandomizedBinderPOMDP(WorldConfig(world_mode=mode))
        assert real.reset(31) == wrapped.reset(31)
        script = [ActionType.MEASURE_STABILITY, ActionType.MEASURE_SPR, ActionType.MEASURE_SEC, ActionType.REDESIGN_STABILITY,
                  ActionType.MEASURE_SPR, ActionType.VALIDATE_ASSAY]
        for kind in script:
            a = ScientificAction(action_type=kind, candidate_id=real.agent_state().active_candidate.candidate_id)
            assert real.available_actions() == wrapped.available_actions()
            if a not in real.available_actions():
                break
            assert real.step(a) == wrapped.step(a)


def test_randomization_changes_lab_conditions_without_exposing_them():
    cfgs = [sample_world_config(s) for s in range(1000, 1200)]
    assert len({round(c.budget, 3) for c in cfgs}) > 50 and {c.world_mode for c in cfgs} == set(BinderWorldMode)
    assert 0.05 < np.mean([c.is_nominal for c in cfgs]) < 0.5
    odd = next(c for c in cfgs if not c.is_nominal)
    env = RandomizedBinderPOMDP(odd)
    state = env.reset(1)
    assert state.resources.budget_remaining == odd.budget and state.resources.sample_remaining == odd.sample
    assert state.resources.spr_instrument_health == odd.initial_spr_health


def test_cost_scale_changes_charges():
    base = RandomizedBinderPOMDP(WorldConfig(BinderWorldMode.SINGLE_FAILURE))
    dear = RandomizedBinderPOMDP(WorldConfig(BinderWorldMode.SINGLE_FAILURE, cost_scale=1.5, spr_cost_scale=2.0))
    for e in (base, dear):
        e.reset(5)
        e.step(ScientificAction(action_type=ActionType.MEASURE_SPR, candidate_id="binder-000"))
    assert dear.agent_state().resources.budget_remaining == pytest.approx(12.0 - 2.0 * 1.5 * 2.0)
    assert base.agent_state().resources.budget_remaining == pytest.approx(10.0)


def test_config_is_a_pure_function_of_seed_and_stage():
    assert sample_world_config(99, 4) == sample_world_config(99, 4)
    assert sample_world_config(99, 4, randomize=False).is_nominal
    assert {sample_world_config(s, 1).world_mode for s in range(50)} == {BinderWorldMode.SINGLE_FAILURE}
    assert set(CURRICULUM[4]) == set(BinderWorldMode)


def test_train_validation_and_held_out_seeds_are_disjoint():
    train, val, held = set(TRAIN_SEEDS[:1000]), set(VAL_SEEDS), set(HELD_OUT_SEEDS)
    assert not (train & val) and not (train & held) and not (val & held)
    assert TRAIN_SEEDS.stop <= VAL_SEEDS.start and VAL_SEEDS.stop <= HELD_OUT_SEEDS.start


def test_observation_depends_only_on_public_inputs():
    env = BinderCampaignEnv(seeds=[11])
    env.reset()
    a = build_observation(env._state, env._summary, env._available)
    b = build_observation(env._state, env._summary, env._available)
    assert np.array_equal(a, b)
    assert np.array_equal(action_mask(env._state, env._available), env.action_masks())
    assert MAX_STEPS == 40


def test_step_cap_forces_a_decision():
    env = BinderCampaignEnv(seeds=[3], randomize=False)
    env.reset()
    env.env._candidates += [env.env._candidates[0]] * (MAX_STEPS)  # public step counter reads 40
    state = env.env.agent_state()
    mask = action_mask(state, env.env.available_actions())
    assert not mask[: ACTION_ORDER.index(ActionType.SELECT)].any() and mask.any()
