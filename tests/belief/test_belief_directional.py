"""Posterior responds in the scientifically expected direction (acceptance gate G5/G6/G9).

Evidence uses the environment's public predictive model through the adapter.
"""

import numpy as np
import pytest
from binder_support import MODEL, act, make_belief, obs

from mirage.core.contracts import ActionType as A


def p(b, field):
    return getattr(b.summary(), field)


def test_sec_showing_aggregation_raises_aggregation():
    b = make_belief(2000)
    before = p(b, "p_aggregation_failure")
    b.observe(MODEL, act(A.MEASURE_SEC), obs(A.MEASURE_SEC, monomer_fraction=0.55))
    after = p(b, "p_aggregation_failure")
    assert after > before and after > 0.9
    assert after < 1.0  # noise leaves uncertainty


def test_clean_sec_lowers_aggregation():
    b = make_belief(2000)
    before = p(b, "p_aggregation_failure")
    b.observe(MODEL, act(A.MEASURE_SEC), obs(A.MEASURE_SEC, monomer_fraction=0.97))
    assert p(b, "p_aggregation_failure") < before and p(b, "p_aggregation_failure") < 0.1


def test_strong_affinity_with_fast_dissociation_separates_affinity_from_kinetics():
    b = make_belief(2000)
    aff0, kin0 = p(b, "p_affinity_failure"), p(b, "p_kinetic_failure")
    b.observe(MODEL, act(A.MEASURE_SPR), obs(A.MEASURE_SPR, log_kd=-9.0, log_koff=-0.5))
    assert p(b, "p_affinity_failure") < aff0 and p(b, "p_affinity_failure") < 0.1
    assert p(b, "p_kinetic_failure") > kin0 and p(b, "p_kinetic_failure") > 0.9


def test_failed_assay_control_raises_assay_invalid():
    b = make_belief(1000)
    before = p(b, "p_assay_invalid")
    b.observe(MODEL, act(A.VALIDATE_ASSAY), obs(A.VALIDATE_ASSAY, control_signal=0.23))
    assert p(b, "p_assay_invalid") > before and p(b, "p_assay_invalid") > 0.95


def test_passing_control_lowers_assay_invalid():
    b = make_belief(1000)
    b.observe(MODEL, act(A.VALIDATE_ASSAY), obs(A.VALIDATE_ASSAY, control_signal=0.86))
    assert p(b, "p_assay_invalid") < 0.05


def test_degraded_spr_quality_is_evidence_of_severe_aggregation():
    b = make_belief(2000)
    b.observe(MODEL, act(A.MEASURE_SPR), obs(A.MEASURE_SPR, quality="degraded", log_kd=-8.7, log_koff=-1.7))
    assert b.particles[:, b.schema.index("monomer_fraction")].max() < 0.45
    assert p(b, "p_aggregation_failure") > 0.99


def test_compound_aggregation_and_kinetics_survive_joint_evidence():
    b = make_belief(3000)
    b.observe(MODEL, act(A.MEASURE_SEC), obs(A.MEASURE_SEC, monomer_fraction=0.6))
    b.observe(MODEL, act(A.MEASURE_SPR), obs(A.MEASURE_SPR, quality="degraded", log_kd=-8.5, log_koff=-1.4))
    s = b.summary()
    assert s.p_aggregation_failure > 0.9 and s.p_kinetic_failure > 0.9
    assert s.p_affinity_failure < 0.3


def test_model_invalid_rises_by_elimination_when_molecule_and_assay_are_good():
    """model_valid is not measured by any assay, so MODEL_INVALID is only reachable by
    eliminating other explanations under a prior conditioned on the downstream failure."""
    b = make_belief(4000, conditioned=True)
    before = p(b, "p_model_invalid")
    for a, o in [
        (A.VALIDATE_ASSAY, obs(A.VALIDATE_ASSAY, control_signal=0.86)),
        (A.MEASURE_EPITOPE, obs(A.MEASURE_EPITOPE, epitope_signal=0.82)),
        (A.ORTHOGONAL_FUNCTION, obs(A.ORTHOGONAL_FUNCTION, orthogonal_function_signal=0.80)),
        (A.MEASURE_STABILITY, obs(A.MEASURE_STABILITY, stability_proxy=0.9)),
        (A.MEASURE_SEC, obs(A.MEASURE_SEC, monomer_fraction=0.97)),
        (A.MEASURE_SPR, obs(A.MEASURE_SPR, log_kd=-9.0, log_koff=-3.5)),
        (A.MEASURE_DEVELOPABILITY, obs(A.MEASURE_DEVELOPABILITY, liability_proxy=0.1)),
    ]:
        b.observe(MODEL, act(a), o)
    assert p(b, "p_model_invalid") > before and p(b, "p_model_invalid") > 0.8
    assert p(b, "p_assay_invalid") < 0.05


def test_model_invalid_does_not_rise_without_ruling_out_other_causes():
    b = make_belief(4000, conditioned=True)
    before = p(b, "p_model_invalid")
    b.observe(MODEL, act(A.VALIDATE_ASSAY), obs(A.VALIDATE_ASSAY, control_signal=0.86))
    assert p(b, "p_model_invalid") < 0.9 and abs(p(b, "p_model_invalid") - before) < 0.25


def test_redesign_transition_improves_target_factor_and_keeps_uncertainty():
    b = make_belief(1500)
    b.observe(MODEL, act(A.MEASURE_SEC), obs(A.MEASURE_SEC, monomer_fraction=0.55))
    before = b.particles.copy()
    agg_before = p(b, "p_aggregation_failure")
    valid_before = p(b, "p_assay_invalid")
    b.apply_redesign(MODEL, act(A.REDESIGN_SOLUBILITY))
    assert not np.array_equal(b.particles, before)  # not the old latents unchanged
    assert p(b, "p_aggregation_failure") < agg_before - 0.2
    assert p(b, "p_aggregation_failure") > 0.0
    # factors the redesign does not touch are carried through the kernel
    assert p(b, "p_assay_invalid") == pytest.approx(valid_before)
    i = b.schema.index("assay_valid")
    assert np.array_equal(b.particles[:, i], before[:, i])


def test_redesign_is_seeded_and_does_not_need_truth():
    def run():
        b = make_belief(300, seed=4)
        b.apply_redesign(MODEL, act(A.REDESIGN_INTERFACE))
        return b.particles.copy()

    assert np.array_equal(run(), run())


def test_adapter_round_trip_and_likelihood_prefers_generating_particle():
    b = make_belief(64)
    row = b.particles[0].copy()
    assert np.allclose(MODEL.to_row(MODEL.to_hypothesis(row)), row)
    rng = np.random.default_rng(1)
    y = MODEL.sample_observation(row, act(A.MEASURE_STABILITY), rng)
    ll = MODEL.log_likelihood(y, b.particles, act(A.MEASURE_STABILITY))
    assert ll.shape == (64,) and np.isfinite(ll[0])
