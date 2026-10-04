import math

import numpy as np
import pytest
from binder_support import MODEL, SCHEMA, act, make_belief, obs
from episode_support import scenario_belief
from policy_helpers import make_actions, make_state

from mirage.belief import (
    FAILURE_FIELDS, DegenerateBeliefError, FailureLocalisation, ParticleBelief, build_certificate,
    posterior_predictive_check, predictive_surprise, summarise_surprises,
)
from mirage.belief.predictive_check import _fisher
from mirage.core.contracts import ActionType as A
from mirage.core.contracts import AgentState

GOOD = {"stability": 0.9, "monomer_fraction": 0.95, "log_kd": -9.0, "log_koff": -3.5, "functional_epitope": 1.0,
        "developability_liability": 0.1, "assay_valid": 1.0, "model_valid": 1.0}


def world(**kw):
    return np.array([{**GOOD, **kw}[f] for f in SCHEMA.factors])


def belief_of(rows, weights=None):
    b = ParticleBelief(SCHEMA, np.array(rows))
    if weights is not None:
        b = ParticleBelief(SCHEMA, np.array(rows), log_weights=np.log(weights))
    return b


# --- FailureLocalisation ----------------------------------------------------------

def test_molecule_probability_is_the_union_not_the_sum():
    both = world(monomer_fraction=0.3, log_koff=-0.5)  # aggregation AND kinetic in the same world
    b = belief_of([both] * 4)
    loc = b.localisation()
    assert loc.mechanism_probabilities["p_aggregation_failure"] == 1.0 and loc.mechanism_probabilities["p_kinetic_failure"] == 1.0
    assert loc.p_molecule_failure == 1.0  # never the naive sum 2.0
    assert loc.p_compound_molecule_failure == 1.0 and loc.leading_locus == "molecule"


def test_union_is_exact_on_a_hand_computed_posterior():
    rows = [world(), world(monomer_fraction=0.3), world(log_koff=-0.5), world(monomer_fraction=0.3, log_koff=-0.5), world(assay_valid=0.0)]
    w = np.array([0.4, 0.1, 0.2, 0.1, 0.2])
    loc = belief_of(rows, w).localisation()
    assert loc.p_molecule_failure == pytest.approx(0.4)  # worlds 1-3
    assert loc.p_experiment_failure == pytest.approx(0.2) and loc.p_model_failure == 0.0
    assert loc.p_no_failure == pytest.approx(0.4) and loc.p_compound_molecule_failure == pytest.approx(0.1)
    mech = loc.mechanism_probabilities
    assert max(mech[f] for f in FAILURE_FIELDS[:6]) <= loc.p_molecule_failure <= sum(mech[f] for f in FAILURE_FIELDS[:6])
    assert loc.locus_joint["none"] == pytest.approx(0.4) and loc.locus_joint["experiment"] == pytest.approx(0.2)
    assert sum(loc.locus_joint.values()) == pytest.approx(1.0)


def test_localisation_on_a_random_belief_respects_the_bounds_and_leaves_summary_untouched():
    b = scenario_belief(512, seed=2)
    loc, summ = b.localisation(), b.summary()
    for f in FAILURE_FIELDS:
        assert loc.mechanism_probabilities[f] == pytest.approx(getattr(summ, f))
    assert set(summ.model_dump()) == set(FAILURE_FIELDS) | {"posterior_entropy", "continuous_means", "continuous_variances", "effective_sample_size"}
    with pytest.raises(Exception):
        FailureLocalisation(**{**loc.model_dump(), "p_molecule_failure": 0.0})  # below its own mechanisms


# --- predictive checks -------------------------------------------------------------

def test_fisher_matches_the_closed_form():
    assert _fisher([0.37]) == pytest.approx(0.37)
    x = -2 * 2 * math.log(0.05)
    assert _fisher([0.05, 0.05]) == pytest.approx(math.exp(-x / 2) * (1 + x / 2))


def test_model_generated_data_is_not_flagged_but_contradiction_is():
    rng = np.random.default_rng(0)
    flagged = 0
    for k in range(40):
        b = make_belief(256, seed=k)
        y = MODEL.sample_observation(b.particles[k % 256], act(A.MEASURE_SEC), rng)
        flagged += predictive_surprise(b, MODEL, act(A.MEASURE_SEC), y, n_samples=32, rng=rng).p_value < 0.05
    assert flagged <= 6  # ~5% expected under a calibrated check
    b = make_belief(512, seed=1)
    wild = predictive_surprise(b, MODEL, act(A.MEASURE_SEC), obs(A.MEASURE_SEC, monomer_fraction=3.0), n_samples=32, rng=rng)
    assert wild.p_value <= 1 / 33 + 1e-12


def test_observation_no_particle_can_generate_is_impossible_and_rejected_by_the_belief():
    clean = ParticleBelief(SCHEMA, np.tile(world(), (64, 1)))
    degraded = obs(A.MEASURE_SPR, quality="degraded", log_kd=-8.6, log_koff=-3.1)
    res = predictive_surprise(clean, MODEL, act(A.MEASURE_SPR), degraded, n_samples=16, rng=np.random.default_rng(0))
    assert res.impossible and res.log_predictive is None and res.p_value == pytest.approx(1 / 17)
    with pytest.raises(DegenerateBeliefError):
        clean.observe(MODEL, act(A.MEASURE_SPR), degraded)
    assert summarise_surprises([res]).verdict == "poorly_explained"


def test_posterior_predictive_check_separates_consistent_from_contradictory_evidence():
    ok = make_belief(2000, seed=0)
    for y in (0.70, 0.72, 0.68):
        ok.observe(MODEL, act(A.MEASURE_SEC), obs(A.MEASURE_SEC, monomer_fraction=y))
    assert posterior_predictive_check(ok, seed=1).verdict == "consistent"
    bad = make_belief(2000, seed=0)
    for y in (0.40, 0.98, 0.42, 0.97):  # the same latent cannot read both
        bad.observe(MODEL, act(A.MEASURE_SEC), obs(A.MEASURE_SEC, monomer_fraction=y))
    rep = posterior_predictive_check(bad, seed=1)
    assert rep.verdict == "poorly_explained" and rep.combined_p_value < 0.01
    assert posterior_predictive_check(make_belief(32)).verdict == "no_evidence"
    assert posterior_predictive_check(bad, seed=1) == rep  # seeded


# --- JustificationCertificate --------------------------------------------------------

def state_with(*done):
    s = make_state(list(done))
    return AgentState(**{**s.model_dump(), "observations": tuple(obs(a, **{"x": 0.0}) for a in done)})


def test_step_zero_certificate_is_not_sufficient_and_reports_what_is_missing():
    b = scenario_belief(512)
    cert = build_certificate(make_state(), b, model=MODEL, available_actions=make_actions(), seed=0, n_samples=24)
    assert not cert.sufficient_for_terminal and not cert.assay_tested
    assert cert.recommended_terminal != A.ABSTAIN  # abstention is not justified at step zero
    assert cert.top_eig_action in {A.MEASURE_STABILITY, A.MEASURE_SEC, A.MEASURE_SPR, A.MEASURE_EPITOPE, A.MEASURE_DEVELOPABILITY, A.VALIDATE_ASSAY, A.ORTHOGONAL_FUNCTION}
    assert cert.alternatives_plausible and cert.missing_evidence
    assert cert.posterior_entropy == pytest.approx(b.mechanism_entropy())


def test_certified_model_invalid_needs_validated_assay_and_no_plausible_alternative():
    b = make_belief(4000, conditioned=True)
    evidence = [(A.VALIDATE_ASSAY, dict(control_signal=0.86)), (A.MEASURE_EPITOPE, dict(epitope_signal=0.82)),
                (A.ORTHOGONAL_FUNCTION, dict(orthogonal_function_signal=0.80)), (A.MEASURE_STABILITY, dict(stability_proxy=0.9)),
                (A.MEASURE_SEC, dict(monomer_fraction=0.97)), (A.MEASURE_SPR, dict(log_kd=-9.0, log_koff=-3.5)),
                (A.MEASURE_DEVELOPABILITY, dict(liability_proxy=0.1))]
    for a, m in evidence:
        b.observe(MODEL, act(a), obs(a, **m))
    st = AgentState(**{**make_state().model_dump(), "observations": tuple(obs(a, **m) for a, m in evidence)})
    cert = build_certificate(st, b, model=MODEL, available_actions=make_actions(), seed=0, n_samples=16)
    assert cert.recommended_terminal == A.MODEL_INVALID and cert.sufficient_for_terminal, cert.missing_evidence
    assert cert.assay_tested and cert.assay_status_resolved and cert.model_distinguishable_from_assay
    assert cert.predictive_check.verdict == "consistent" and cert.localisation.leading_locus == "model"
    # same evidence but never validating the assay: the claim is no longer justified
    b2 = make_belief(4000, conditioned=True)
    b2.observe(MODEL, act(A.MEASURE_STABILITY), obs(A.MEASURE_STABILITY, stability_proxy=0.9))
    c2 = build_certificate(state_with(A.MEASURE_STABILITY), b2, seed=0)
    assert not c2.sufficient_for_terminal and c2.recommended_terminal not in (A.SELECT, A.MODEL_INVALID)


def test_broken_assay_recommends_supportable_abstention_not_a_prior_driven_select():
    b = scenario_belief(2000, seed=1)  # in this prior only good molecules have broken assays
    b.observe(MODEL, act(A.VALIDATE_ASSAY), obs(A.VALIDATE_ASSAY, control_signal=0.23))
    cert = build_certificate(state_with(A.VALIDATE_ASSAY), b, seed=0)
    assert cert.localisation.p_experiment_failure > 0.9 and not cert.model_distinguishable_from_assay
    assert cert.recommended_terminal == A.ABSTAIN  # SELECT is gated: no assay-independent function evidence


def test_certificate_is_public_json_without_particles_and_handles_certainty():
    cert = build_certificate(state_with(A.VALIDATE_ASSAY), ParticleBelief(SCHEMA, np.tile(world(), (32, 1))), seed=0, check_predictive=False)
    assert cert.posterior_odds_vs_runner_up is None and cert.leading_diagnosis == "no failure"
    dumped = cert.model_dump_json()
    assert "particles" not in dumped and "NaN" not in dumped and "Infinity" not in dumped
