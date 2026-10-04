import time

import numpy as np
import pytest
from binder_support import MODEL, SCHEMA, act, make_belief, obs
from episode_support import scenario_belief
from policy_helpers import ASSAYS, TERMINALS, make_actions, make_state

from mirage.belief import ParticleBelief
from mirage.core.contracts import ActionType as A
from mirage.core.contracts import AgentState, ResourceState
from mirage.environments.binder import BinderBioPOMDP, BinderWorldMode
from mirage.environments.binder.environment import _COSTS
from mirage.policies import (
    DEFAULT_ACTION_COSTS,
    ActionCost,
    LookaheadConfig,
    LookaheadPolicy,
    PolicyError,
    ScientificPolicy,
    SPRHealthModel,
)

FAST = dict(depth=2, samples=(4, 4, 3), measurement_beam=(7, 3, 2))


def policy(belief, seed=0, **cfg):
    return LookaheadPolicy(MODEL, lambda: belief, seed=seed, config=LookaheadConfig(**{**FAST, **cfg}))


def state(done=(), health=1.0, budget=12.0, sample=8.0, terminal=False):
    s = make_state(done)
    r = ResourceState(budget_remaining=budget, sample_remaining=sample, simulated_time=0, spr_instrument_health=health)
    return AgentState(**{**s.model_dump(), "resources": r.model_dump(), "terminal": terminal})


def good_belief(n=64, **overrides):
    """Every particle is the same good, valid world (certain belief)."""
    row = {"stability": 0.9, "monomer_fraction": 0.95, "log_kd": -9.0, "log_koff": -3.5, "functional_epitope": 1.0,
           "developability_liability": 0.1, "assay_valid": 1.0, "model_valid": 1.0, **overrides}
    return ParticleBelief(SCHEMA, np.tile([row[f] for f in SCHEMA.factors], (n, 1)))


# --- contract ---------------------------------------------------------------

def test_shares_the_policy_contract_and_returns_an_available_action():
    import inspect
    b = make_belief(256)
    pol = policy(b)
    assert issubclass(LookaheadPolicy, ScientificPolicy)
    assert inspect.signature(LookaheadPolicy.choose_action) == inspect.signature(ScientificPolicy.choose_action)
    acts = make_actions()
    assert pol.choose_action(state(), b.summary(), acts) in acts


def test_deterministic_given_seed_and_reset_replays():
    b = make_belief(256, conditioned=True)
    st, acts = state(), make_actions()
    a1 = [policy(b, seed=5).choose_action(st, b.summary(), acts) for _ in range(2)]
    assert a1[0] == a1[1]
    pol = policy(b, seed=5)
    first = pol.choose_action(st, b.summary(), acts)
    q1 = dict(pol.last_plan.q_values)
    pol.reset()
    assert pol.choose_action(st, b.summary(), acts) == first and pol.last_plan.q_values == q1


def test_does_not_mutate_the_belief_and_rejects_a_stale_handle():
    b = make_belief(256)
    before = (b.particles.copy(), b.log_weights)
    policy(b).choose_action(state(), b.summary(), make_actions())
    assert np.array_equal(b.particles, before[0]) and np.array_equal(b.log_weights, before[1])
    other = make_belief(256, seed=3)
    other.observe(MODEL, act(A.MEASURE_SEC), obs(A.MEASURE_SEC, monomer_fraction=0.5))
    with pytest.raises(PolicyError, match="out of sync"):
        policy(other).choose_action(state(), b.summary(), make_actions())


def test_terminal_state_and_empty_actions_raise():
    b = make_belief(64)
    with pytest.raises(PolicyError):
        policy(b).choose_action(state(terminal=True), b.summary(), make_actions())
    with pytest.raises(PolicyError):
        policy(b).choose_action(state(), b.summary(), ())


def test_depth_must_fit_the_sample_schedule():
    with pytest.raises(ValueError):
        LookaheadPolicy(MODEL, lambda: make_belief(8), config=LookaheadConfig(depth=4))


# --- hypothetical particles only (no truth) -----------------------------------

def test_only_hypothetical_particles_are_simulated():
    class Spy:
        def __init__(self):
            self.schema, self.sources, self.children = MODEL.schema, [], []

        def sample_observation(self, particle, action, rng):
            self.sources.append(tuple(particle))
            return MODEL.sample_observation(particle, action, rng)

        def log_likelihood(self, *a):
            return MODEL.log_likelihood(*a)

        def redesign(self, particles, action, rng):
            out = MODEL.redesign(particles, action, rng)
            self.children.extend(map(tuple, out))
            return out

    spy, b = Spy(), make_belief(128, conditioned=True)
    obs_ = obs(A.MEASURE_STABILITY, stability_proxy=0.2)
    b.observe(MODEL, act(A.MEASURE_STABILITY), obs_)
    pol = LookaheadPolicy(spy, lambda: b, config=LookaheadConfig(**{**FAST, "planning_particles": None}))
    pol.choose_action(state([A.MEASURE_STABILITY]), b.summary(), make_actions())
    known = {tuple(r) for r in b.particles} | set(spy.children)
    assert spy.sources and all(s in known for s in spy.sources)


# --- evidence gates and long-horizon reasoning ---------------------------------

def test_plans_the_control_before_a_positive_claim_then_claims():
    """Certain good belief: SELECT is gated until assay integrity is established, so the
    planner runs VALIDATE_ASSAY first (long-horizon), and SELECTs once it has been run."""
    b = good_belief()
    first = policy(b).choose_action(state(), b.summary(), make_actions()).action_type
    assert first == A.VALIDATE_ASSAY
    done = policy(b).choose_action(state([A.VALIDATE_ASSAY]), b.summary(), make_actions()).action_type
    assert done == A.SELECT


def test_never_abstains_at_step_zero_and_may_after_a_diagnostic():
    b = good_belief(assay_valid=0.0)  # assay certainly broken
    only_terminals = make_actions(TERMINALS)
    assert policy(b).choose_action(state(), b.summary(), only_terminals).action_type != A.ABSTAIN
    after = policy(b).choose_action(state([A.VALIDATE_ASSAY]), b.summary(), only_terminals).action_type
    assert after == A.ABSTAIN  # broken assay, nothing independent to establish the molecule


def test_blind_redesign_is_not_planned_without_evidence_of_its_target_failure():
    b = scenario_belief(512)  # no single mechanism is probable yet (each < 0.5)
    assert max(v for k, v in b.failure_probabilities().items() if k != 'p_model_invalid') < 0.5
    pol = policy(b)
    pol.choose_action(state(), b.summary(), make_actions())
    assert not any(t.value.startswith("REDESIGN") for t in pol.last_plan.q_values)
    folded = make_belief(512)
    folded.observe(MODEL, act(A.MEASURE_STABILITY), obs(A.MEASURE_STABILITY, stability_proxy=0.15))
    pol2 = policy(folded)
    pol2.choose_action(state([A.MEASURE_STABILITY]), folded.summary(), make_actions())
    assert A.REDESIGN_STABILITY in pol2.last_plan.q_values and A.REDESIGN_INTERFACE not in pol2.last_plan.q_values


def test_spr_is_not_planned_once_the_instrument_is_below_its_usable_health():
    b = make_belief(256, conditioned=True)
    healthy, damaged = policy(b), policy(b)
    healthy.choose_action(state(health=1.0), b.summary(), make_actions())
    damaged.choose_action(state(health=0.55), b.summary(), make_actions())
    assert A.MEASURE_SPR in healthy.last_plan.q_values
    assert A.MEASURE_SPR not in damaged.last_plan.q_values


def test_unaffordable_assays_are_not_planned_and_only_terminals_remain_when_broke():
    b = make_belief(256)
    pol = policy(b)
    pol.choose_action(state(budget=1.2, sample=8), b.summary(), make_actions())
    assert A.MEASURE_SPR not in pol.last_plan.q_values and A.ORTHOGONAL_FUNCTION not in pol.last_plan.q_values
    assert policy(b).choose_action(state(budget=0.0), b.summary(), make_actions(TERMINALS)).action_type in TERMINALS


def test_expensive_assays_are_avoided_when_costs_are_raised():
    b = make_belief(256, conditioned=True)
    base = policy(b)
    best = base.choose_action(state(), b.summary(), make_actions()).action_type
    costs = {**DEFAULT_ACTION_COSTS, best: ActionCost(11.0, 0.1, 5.0)}
    pricey = LookaheadPolicy(MODEL, lambda: b, config=LookaheadConfig(**FAST), costs=costs)
    assert pricey.choose_action(state(), b.summary(), make_actions()).action_type != best


def test_cost_penalty_weights_matter():
    b = make_belief(256, conditioned=True)
    free = policy(b, budget_penalty=0.0, sample_penalty=0.0, time_penalty=0.0)
    free.choose_action(state(), b.summary(), make_actions())
    dear = policy(b, budget_penalty=0.5, sample_penalty=0.5, time_penalty=0.5)
    dear.choose_action(state(), b.summary(), make_actions())
    assert free.last_plan.q_values[A.MEASURE_SPR] > dear.last_plan.q_values[A.MEASURE_SPR] + 0.5


def test_common_random_numbers_make_deeper_plans_dominate_one_step_plans():
    b = make_belief(256, conditioned=True)
    d1, d2 = policy(b, depth=1), policy(b, depth=2)
    d1.choose_action(state(), b.summary(), make_actions())
    d2.choose_action(state(), b.summary(), make_actions())
    for t, q1 in d1.last_plan.q_values.items():
        if t in d2.last_plan.q_values and t in ASSAYS:
            assert d2.last_plan.q_values[t] >= q1 - 0.03


# --- resource / SPR model is pinned to the environment ---------------------------

def test_default_costs_equal_the_environment_resource_model():
    assert {k: (c.budget, c.sample, c.time) for k, c in DEFAULT_ACTION_COSTS.items()} == {
        k: (c.budget, c.sample, c.time) for k, c in _COSTS.items()
    }


def test_spr_health_model_matches_the_environment():
    spr = SPRHealthModel()
    env = BinderBioPOMDP(BinderWorldMode.COMPOUND_FAILURE)
    env.reset(4)
    action = next(a for a in env.available_actions() if a.action_type == A.MEASURE_SPR)
    first = env.step(action)
    assert first.observation.quality == "degraded"
    assert 1.0 - first.state.resources.spr_instrument_health == pytest.approx(spr.damage)
    good = BinderBioPOMDP(BinderWorldMode.ASSAY_FAILURE)  # a clean molecule never damages the instrument
    good.reset(4)
    clean = good.step(next(a for a in good.available_actions() if a.action_type == A.MEASURE_SPR))
    assert clean.observation.quality == "nominal" and clean.state.resources.spr_instrument_health == 1.0
    for health, degraded in ((spr.min_usable_health - 0.02, True), (spr.min_usable_health + 0.02, False)):
        good.reset(4)
        good._resources = good._resources.model_copy(update={"spr_instrument_health": health})  # test-only poke
        obs_ = good.step(next(a for a in good.available_actions() if a.action_type == A.MEASURE_SPR)).observation
        assert (obs_.quality == "degraded") is degraded


# --- latency ----------------------------------------------------------------------

def test_decision_latency_depth2_and_depth3():
    b = make_belief(512, conditioned=True)
    st, acts = state(), make_actions()
    for cfg, ceiling in ((LookaheadConfig(), 3.0), (LookaheadConfig(depth=3, samples=(4, 3, 3), measurement_beam=(7, 3, 2)), 3.0)):
        pol = LookaheadPolicy(MODEL, lambda: b, config=cfg)
        pol.choose_action(st, b.summary(), acts)  # warm-up
        t0 = time.perf_counter()
        pol.choose_action(st, b.summary(), acts)
        wall = time.perf_counter() - t0
        assert wall < ceiling, (cfg.depth, wall)
        assert pol.last_plan.seconds == pytest.approx(wall, rel=0.25, abs=0.05)
        assert pol.last_plan.likelihood_sweeps > 0
