import time

import numpy as np
import pytest
from binder_support import MODEL, act, make_belief, obs
from policy_helpers import ASSAYS, TERMINALS, make_actions, make_state

from mirage.belief import expected_information_gain
from mirage.core.contracts import ActionType as A
from mirage.core.contracts import AgentState
from mirage.policies import GreedyEIGPolicy, PolicyError, ScientificPolicy


def policy(belief, **kw):
    kw.setdefault("seed", 1)
    return GreedyEIGPolicy(MODEL, lambda: belief, **kw)


def eig(belief, t, seed=0, n=64, **kw):
    return expected_information_gain(belief, MODEL, act(t), n_samples=n, rng=np.random.default_rng(seed), **kw)


# --- estimator ---------------------------------------------------------------

def test_eig_is_bounded_nonnegative_and_discriminates_assays():
    b = make_belief(512)
    h0 = b.mechanism_entropy()
    scores = {t: eig(b, t).eig for t in ASSAYS}
    assert all(-0.05 <= e <= h0 for e in scores.values())
    # a single-threshold readout cannot remove more than its one mechanism's entropy
    assert scores[A.MEASURE_STABILITY] < np.log(2) + 0.1
    assert scores[A.MEASURE_SPR] > scores[A.MEASURE_SEC] > 0.1  # SPR informs two mechanisms


def test_eig_matches_converged_value_at_default_particle_count():
    """Regression for finite-particle bias: raw joint-pattern EIG overstated SPR ~2x at N=512."""
    small = np.mean([eig(make_belief(512, seed=s), A.MEASURE_SPR, seed=s).eig for s in range(3)])
    big = np.mean([eig(make_belief(6000, seed=s), A.MEASURE_SPR, seed=s, n=16).eig for s in range(2)])
    assert abs(small - big) < 0.35 * big


def test_tempering_engages_only_when_posterior_would_collapse():
    b = make_belief(512)
    assert eig(b, A.MEASURE_SPR).tempering < 1.0
    assert eig(b, A.MEASURE_STABILITY).tempering == 1.0
    loose = eig(b, A.MEASURE_SPR, min_posterior_ess=0.0)
    assert loose.tempering == 1.0 and loose.eig > eig(b, A.MEASURE_SPR).eig  # untempered is the biased one


def test_eig_deterministic_given_seed_and_does_not_mutate_belief():
    b = make_belief(256)
    before = (b.particles.copy(), b.log_weights)
    assert eig(b, A.MEASURE_SEC, seed=5) == eig(b, A.MEASURE_SEC, seed=5)
    assert eig(b, A.MEASURE_SEC, seed=5) != eig(b, A.MEASURE_SEC, seed=6)
    assert np.array_equal(b.particles, before[0]) and np.array_equal(b.log_weights, before[1])


def test_eig_falls_once_the_question_is_answered():
    b = make_belief(1500)
    before = eig(b, A.VALIDATE_ASSAY).eig
    b.observe(MODEL, act(A.VALIDATE_ASSAY), obs(A.VALIDATE_ASSAY, control_signal=0.86))
    assert eig(b, A.VALIDATE_ASSAY).eig < 0.25 * before


def test_eig_is_zero_when_belief_is_certain():
    p = make_belief(64).particles.copy()
    p[:] = p[0]
    from mirage.belief import ParticleBelief
    b = ParticleBelief(make_belief(8).schema, p)
    assert b.mechanism_entropy() == 0.0
    assert eig(b, A.MEASURE_SPR).eig == pytest.approx(0.0, abs=1e-9)


# --- myopia ------------------------------------------------------------------

class SpyModel:
    """Records every call so tests can prove the policy is strictly one-step."""

    def __init__(self, inner):
        self.inner, self.schema = inner, inner.schema
        self.sampled, self.scored, self.redesigned = [], [], 0

    def sample_observation(self, particle, action, rng):
        self.sampled.append(action.action_type)
        return self.inner.sample_observation(particle, action, rng)

    def log_likelihood(self, observation, particles, action):
        self.scored.append((action.action_type, observation.action_type))
        return self.inner.log_likelihood(observation, particles, action)

    def redesign(self, *a, **k):
        self.redesigned += 1
        return self.inner.redesign(*a, **k)


def test_policy_is_myopic_single_observation_per_sample_no_lookahead():
    spy, b = SpyModel(MODEL), make_belief(128)
    pol = GreedyEIGPolicy(spy, lambda: b, n_samples=8, seed=0)
    pol.choose_action(make_state(), b.summary(), make_actions())
    assert len(spy.sampled) == 8 * len(ASSAYS)  # exactly n_samples per assay, nothing deeper
    assert all(a == o for a, o in spy.scored)  # each likelihood scores that same action's observation
    assert len(spy.scored) == len(spy.sampled)
    assert spy.redesigned == 0  # redesign/terminal never simulated
    assert set(spy.sampled) == set(ASSAYS)


# --- decisions ---------------------------------------------------------------

def test_picks_argmax_and_is_deterministic():
    b = make_belief(512)
    pol = policy(b)
    a = pol.choose_action(make_state(), b.summary(), make_actions())
    assert a.action_type == max(pol.last_scores, key=lambda t: pol.last_scores[t].score)
    assert a.action_type in ASSAYS
    b2, pol2 = make_belief(512), policy(make_belief(512))
    pol2.belief_source = lambda: b2
    assert pol2.choose_action(make_state(), b2.summary(), make_actions()) == a


def test_reset_replays_decision_stream():
    b = make_belief(256)
    pol = policy(b)
    first = [pol.choose_action(make_state(), b.summary(), make_actions()) for _ in range(3)]
    scores = dict(pol.last_scores)
    pol.reset()
    again = [pol.choose_action(make_state(), b.summary(), make_actions()) for _ in range(3)]
    assert first == again and scores == pol.last_scores


def test_decision_depends_on_belief_not_on_anything_else():
    """Same public state and actions; a different belief gives a different action."""
    fresh, resolved = make_belief(1500), make_belief(1500)
    resolved.observe(MODEL, act(A.VALIDATE_ASSAY), obs(A.VALIDATE_ASSAY, control_signal=0.86))
    acts = make_actions([A.VALIDATE_ASSAY, A.MEASURE_SEC] + TERMINALS)
    pick_fresh = policy(fresh, n_samples=64).choose_action(make_state(), fresh.summary(), acts)
    pick_resolved = policy(resolved, n_samples=64).choose_action(make_state(), resolved.summary(), acts)
    assert pick_fresh.action_type == A.VALIDATE_ASSAY  # assay validity is a full 50/50 unknown
    assert pick_resolved.action_type == A.MEASURE_SEC  # control already answered: EIG ~ 0


def test_stale_belief_handle_is_rejected():
    live, stale = make_belief(256), make_belief(256, seed=9)
    stale.observe(MODEL, act(A.MEASURE_SEC), obs(A.MEASURE_SEC, monomer_fraction=0.5))
    with pytest.raises(PolicyError, match="out of sync"):
        policy(stale).choose_action(make_state(), live.summary(), make_actions())


def test_only_available_actions_are_considered_and_redesign_is_never_chosen():
    b = make_belief(256)
    pol = policy(b)
    acts = make_actions([A.MEASURE_SEC, A.REDESIGN_SOLUBILITY] + TERMINALS)
    chosen = pol.choose_action(make_state(), b.summary(), acts)
    assert chosen in acts and set(pol.last_scores) == {A.MEASURE_SEC}
    only_redesign = make_actions([A.REDESIGN_SOLUBILITY, A.REJECT])
    assert policy(b).choose_action(make_state(), b.summary(), only_redesign).action_type == A.REJECT
    with pytest.raises(PolicyError):
        policy(b).choose_action(make_state(), b.summary(), make_actions([A.REDESIGN_SOLUBILITY]))


def test_stops_and_decides_when_no_assay_is_informative():
    b = make_belief(512)
    pol = policy(b, min_eig=50.0)  # nothing can reach this
    a = pol.choose_action(make_state(), b.summary(), make_actions())
    assert a.action_type in TERMINALS


def test_cost_aware_variant_shifts_choice_to_cheaper_assay():
    b = make_belief(512)
    base = policy(b)
    best = base.choose_action(make_state(), b.summary(), make_actions()).action_type
    cheap = policy(b, costs={best: 1e4})
    aware = cheap.choose_action(make_state(), b.summary(), make_actions()).action_type
    assert aware != best
    scores = cheap.last_scores
    assert scores[best].cost == 1e4 and scores[best].score < scores[best].eig
    with pytest.raises(ValueError):
        policy(b, costs={best: 0.0})


def test_same_contract_as_other_baselines_and_decisions_are_available_actions():
    import inspect
    assert issubclass(GreedyEIGPolicy, ScientificPolicy)
    assert inspect.signature(GreedyEIGPolicy.choose_action) == inspect.signature(ScientificPolicy.choose_action)
    b = make_belief(128)
    acts = make_actions()
    assert policy(b, n_samples=8).choose_action(make_state(), b.summary(), acts) in acts


def test_terminal_state_raises():
    b = make_belief(64)
    with pytest.raises(PolicyError):
        policy(b).choose_action(make_state(terminal=True), b.summary(), make_actions())


# --- end-to-end with a harness that plays the environment ---------------------

def run_episode(true_row, belief, pol, seed, max_steps=12):
    """The harness knows true_row to generate observations; pol and belief never do."""
    rng = np.random.default_rng(seed)
    obs_log, done = [], False
    state = make_state()
    for _ in range(max_steps):
        state = AgentState(**{**state.model_dump(), "observations": tuple(obs_log)})
        a = pol.choose_action(state, belief.summary(), make_actions())
        if a.action_type in TERMINALS:
            return a, belief
        y = MODEL.sample_observation(true_row, a, rng)
        obs_log.append(y)
        belief.observe(MODEL, a, y)
    return None, belief


def test_end_to_end_recovers_compound_failure_from_public_observations_only():
    truth = np.array([0.8, 0.6, -9.0, -1.2, 1.0, 0.2, 1.0, 1.0])  # aggregated + fast koff, strong affinity
    belief = make_belief(1024, seed=3, ess_threshold=0.5)
    pol = policy(belief, n_samples=32, min_eig=0.05)
    decision, belief = run_episode(truth, belief, pol, seed=11)
    s = belief.summary()
    assert decision is not None and decision.action_type == A.REJECT
    assert s.p_aggregation_failure > 0.8 and s.p_kinetic_failure > 0.8 and s.p_affinity_failure < 0.2


# --- performance -------------------------------------------------------------

def test_one_decision_is_interactive_at_default_settings():
    b = make_belief(512)
    pol = policy(b, n_samples=64)
    acts, st, summ = make_actions(), make_state(), b.summary()
    pol.choose_action(st, summ, acts)  # warm up
    t0 = time.perf_counter()
    pol.choose_action(st, summ, acts)
    wall = time.perf_counter() - t0
    assert pol.last_decision_seconds == pytest.approx(wall, rel=0.2, abs=0.02)
    assert wall < 1.5  # generous CI ceiling; ~0.2 s typical on a laptop


# --- structured multi-output observations ------------------------------------

def test_hypothetical_spr_outcomes_are_structured_multi_output_observations():
    b = make_belief(256)
    rng = np.random.default_rng(0)
    y = MODEL.sample_observation(b.particles[0], act(A.MEASURE_SPR), rng)
    assert y.action_type == A.MEASURE_SPR and set(y.measurements) == {"log_kd", "log_koff"}
    assert isinstance(y.quality, str) and y.quality


def test_eig_likelihood_couples_every_output_and_rejects_malformed_outcomes():
    b = make_belief(256)
    a = act(A.MEASURE_SPR)
    y = MODEL.sample_observation(b.particles[3], a, np.random.default_rng(1))
    base = MODEL.log_likelihood(y, b.particles, a)
    shifted_koff = obs(A.MEASURE_SPR, quality=y.quality, log_kd=y.measurements["log_kd"], log_koff=y.measurements["log_koff"] + 1.0)
    assert not np.allclose(base[np.isfinite(base)], MODEL.log_likelihood(shifted_koff, b.particles, a)[np.isfinite(base)])
    only_kd = obs(A.MEASURE_SPR, quality=y.quality, log_kd=y.measurements["log_kd"])
    assert np.all(np.isneginf(MODEL.log_likelihood(only_kd, b.particles, a)))


def test_spr_eig_exceeds_each_single_output_view_of_the_same_mechanisms():
    """SPR informs affinity and kinetics jointly, so it must out-score the one-output assays
    that each inform only one of the mechanisms it covers (here: stability and epitope)."""
    b = make_belief(512)
    spr = eig(b, A.MEASURE_SPR).eig
    assert spr > eig(b, A.MEASURE_STABILITY).eig and spr > eig(b, A.MEASURE_EPITOPE).eig
