"""F1: transparent reward, separate from scientific evaluation."""

import ast
import pathlib

import numpy as np
import pytest

pytest.importorskip("gymnasium")

from mirage.core import ActionType as A
from mirage.core import ScientificAction
from mirage.environments.binder import BinderWorldMode as W
from mirage.rl.binder_env import RandomizedBinderPOMDP
from mirage.rl.gym_env import BinderCampaignEnv
from mirage.rl.observation import ACTION_ORDER
from mirage.rl.randomization import WorldConfig
from mirage.rl.reward import RewardConfig, step_reward


def decide(mode: W, decision: A, seed: int = 3) -> float:
    env = RandomizedBinderPOMDP(WorldConfig(mode))
    env.reset(seed)
    env.step(ScientificAction(action_type=decision, candidate_id="binder-000"))
    return env.terminal_utility()


@pytest.mark.parametrize("mode,best", [(W.MODEL_FAILURE, A.MODEL_INVALID), (W.MIXED, A.REJECT)])
def test_unique_correct_decisive_action_is_rewarded_and_others_are_not(mode, best):
    utilities = {d: decide(mode, d) for d in (A.SELECT, A.REJECT, A.MODEL_INVALID, A.ABSTAIN)}
    assert utilities[best] == 1.0
    assert all(v < 1.0 for d, v in utilities.items() if d != best)


@pytest.mark.parametrize("mode", [W.ASSAY_FAILURE, W.COMPOUND_FAILURE, W.SINGLE_FAILURE])
def test_when_nothing_decisive_is_correct_abstaining_pays_less_than_a_win_and_more_than_a_wrong_call(mode):
    cfg = RewardConfig()
    assert decide(mode, A.ABSTAIN) == cfg.abstain_value < 1.0
    assert all(decide(mode, d) == -1.0 for d in (A.SELECT, A.REJECT, A.MODEL_INVALID))


@pytest.mark.parametrize("mode", [W.MODEL_FAILURE, W.MIXED])
def test_abstaining_when_a_decisive_answer_was_correct_is_a_neutral_hedge_not_a_win(mode):
    assert decide(mode, A.ABSTAIN) == 0.0


@pytest.mark.parametrize("mode", list(W))
def test_blind_abstention_is_never_worth_a_full_win(mode):
    assert decide(mode, A.ABSTAIN) < 1.0


def test_terminal_utility_is_zero_before_a_decision():
    env = RandomizedBinderPOMDP(WorldConfig(W.MIXED))
    env.reset(1)
    assert env.terminal_utility() == 0.0


def test_info_shaping_telescopes_so_cycles_cannot_farm_it():
    cfg = RewardConfig(c_budget=0, c_sample=0, c_time=0, c_spr=0, c_redesign=0)
    entropies = [3.0, 2.0, 2.8, 1.5, 2.2, 1.0]
    total = sum(step_reward(cfg, entropy_before=a, entropy_after=b, budget_spent=0, sample_spent=0, time_elapsed=0,
                            spr_health_lost=0, is_redesign=False, redesign_count=0, terminal_utility=None)[0]
                for a, b in zip(entropies, entropies[1:]))
    assert total == pytest.approx(cfg.lambda_info * (entropies[0] - entropies[-1]))


def test_reward_terms_sum_to_reward_and_costs_are_negative():
    cfg = RewardConfig()
    r, t = step_reward(cfg, entropy_before=2.0, entropy_after=2.0, budget_spent=2.0, sample_spent=1.0, time_elapsed=1.0,
                       spr_health_lost=0.28, is_redesign=True, redesign_count=4, terminal_utility=1.0)
    assert r == pytest.approx(sum(t.values()))
    assert t["budget"] == pytest.approx(-0.04) and t["instrument"] == pytest.approx(-0.14) and t["redesign"] == -cfg.c_redesign
    assert t["terminal"] == 1.0 and t["info_gain"] == 0.0


def test_free_redesigns_are_not_penalised():
    cfg = RewardConfig()
    _, t = step_reward(cfg, entropy_before=1, entropy_after=1, budget_spent=0, sample_spent=0, time_elapsed=0,
                       spr_health_lost=0, is_redesign=True, redesign_count=cfg.free_redesigns, terminal_utility=None)
    assert t["redesign"] == 0.0


def test_gym_episode_return_equals_sum_of_step_rewards():
    env = BinderCampaignEnv(seeds=[21], randomize=False)
    env.reset()
    total, done = 0.0, False
    for a in (A.MEASURE_SEC, A.MEASURE_SPR, A.VALIDATE_ASSAY, A.ABSTAIN):
        _, r, done, _, info = env.step(ACTION_ORDER.index(a))
        total += r
    assert done and info["episode_summary"]["return"] == pytest.approx(total)


def test_rl_package_never_imports_the_privileged_evaluator_or_provenance_truth():
    root = pathlib.Path(__file__).resolve().parents[2] / "src" / "mirage" / "rl"
    banned = ("mirage.evaluation", "mirage.provenance", "mirage.api")
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = [n.name for n in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not [n for n in names if n.startswith(banned)], f"{path.name} imports {names}"
