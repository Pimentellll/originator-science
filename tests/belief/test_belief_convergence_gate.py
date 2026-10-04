"""Posterior-convergence regression tests (B4A).

Fixed public traces, Baseline-V1 prior and label rules, and exact importance-sampling references
(tests/fixtures/belief_traces). Tolerances are the ones frozen in
docs/validation/POSTERIOR_CONVERGENCE_GATE.md and were fixed before any remedy was evaluated.
"""

import json

import numpy as np
import pytest
from v1_config_support import FIXTURES, MODEL_V1, PRIOR_V1, SCHEMA_V1, fresh_belief, load_traces, replay

from mirage.belief import FAILURE_FIELDS, DegenerateBeliefError, ParticleBelief, systematic_resample
from mirage.core.contracts import ActionType as A
from mirage.core.contracts import ScientificAction, ScientificObservation

TOL = 0.05  # gate: |marginal - reference| and seed standard deviation
TRACES = load_traces("v1_public_traces.json")
EXACT = json.loads((FIXTURES / "exact_references.json").read_text())
GREEDY = TRACES["invalid_biological_model-50000-greedy_eig"]
IDX = {f: i for i, f in enumerate(FAILURE_FIELDS)}


def marginals(trace, k, n, seeds, **kw):
    return np.array([[replay(trace[:k], n, s, **kw)[0].failure_probabilities()[f] for f in FAILURE_FIELDS] for s in range(seeds)])


def references(min_ess=800):
    return [(key, v) for key, v in EXACT.items() if v["ess"] >= min_ess]


@pytest.mark.parametrize("key,ref", references(), ids=[k for k, _ in references()])
def test_tempered_posterior_matches_exact_reference_at_512_particles(key, ref):
    name, k = key.rsplit("|", 1)
    m = marginals(TRACES[name], int(k), 512, 8)
    exact = np.array([ref["marginals"][f] for f in FAILURE_FIELDS])
    # reference Monte Carlo error is sqrt(.25 / ESS) <= 0.02 here; the gate adds its own 0.05
    assert np.abs(m.mean(0) - exact).max() <= TOL + 0.02, dict(zip(FAILURE_FIELDS, (m.mean(0) - exact).round(3)))
    assert m.std(0).max() <= TOL


def test_full_invalid_model_trace_is_certain_and_seed_stable_at_512():
    m = marginals(GREEDY, len(GREEDY), 512, 8)
    assert m[:, IDX["p_model_invalid"]].min() >= 0.95 and m[:, IDX["p_developability_failure"]].max() <= 0.05
    assert m.std(0).max() <= TOL


def test_legacy_one_shot_resampling_violates_the_gate_on_the_same_evidence():
    """Documents the failure mode: sharp evidence collapses plain SIR onto a few ancestors."""
    m = marginals(GREEDY, 1, 512, 12, tempering=False)
    assert m[:, IDX["p_developability_failure"]].std() > 0.15


def test_marginals_do_not_depend_on_the_ordering_of_the_initial_particle_array():
    sd = []
    for permuted in (False, True):
        vals = []
        for seed in range(10):
            b = fresh_belief(512, seed)
            if permuted:
                order = np.random.default_rng(1000 + seed).permutation(512)
                b = ParticleBelief(SCHEMA_V1, b.particles[order], seed=seed, prior=PRIOR_V1)
            for a, y in GREEDY[:3]:
                b.observe(MODEL_V1, a, y)
            vals.append(b.failure_probabilities()["p_developability_failure"])
        sd.append((np.mean(vals), np.std(vals)))
    assert abs(sd[0][0] - sd[1][0]) <= 0.06 and max(s for _, s in sd) <= TOL


def test_initial_belief_reproduces_the_conditioned_prior_marginals():
    """No accidental mechanism correlations beyond the declared 'at least one failure' conditioning."""
    b = fresh_belief(40000, 0)
    z = PRIOR_V1.sample(np.random.default_rng(99), 400000)
    ref = SCHEMA_V1.failure_indicators(z).mean(0)
    got = np.array([b.failure_probabilities()[f] for f in FAILURE_FIELDS])
    assert np.abs(got - ref).max() < 0.01


def test_systematic_resampling_is_low_variance_and_order_free():
    rng = np.random.default_rng(0)
    w = rng.dirichlet(np.ones(50))
    counts = np.bincount(systematic_resample(w, rng, size=1000), minlength=50)
    assert np.all(np.abs(counts - 1000 * w) < 1.0 + 1e-9)  # within one copy of N * w
    perm = rng.permutation(50)
    c2 = np.bincount(systematic_resample(w[perm], np.random.default_rng(1), size=1000), minlength=50)
    assert np.all(np.abs(c2 - 1000 * w[perm]) < 1.0 + 1e-9)


def test_tempering_keeps_weights_healthy_and_uses_more_stages_for_sharper_evidence():
    b = fresh_belief(1024, 0)
    sharp = b.observe(MODEL_V1, *GREEDY[0])  # 2-D SPR reading: ~0.15% of the prior
    assert sharp.stages > 1 and sharp.ess_after >= 0.5 * 1024 - 1
    mild = fresh_belief(1024, 1).observe(
        MODEL_V1, ScientificAction(action_type=A.VALIDATE_ASSAY, candidate_id="binder-000"),
        ScientificObservation(action_type=A.VALIDATE_ASSAY, candidate_id="binder-000", measurements={"control_signal": 0.55}, quality="nominal"),
    )
    assert mild.stages <= sharp.stages
    assert np.isfinite(sharp.log_evidence) and sharp.max_weight > 0


def test_impossible_evidence_still_raises_and_leaves_the_belief_unchanged():
    b = fresh_belief(256, 0)
    before = (b.particles.copy(), b.log_weights)
    impossible = ScientificObservation(action_type=A.MEASURE_SPR, candidate_id="binder-000", measurements={"log_kd": -8.0, "log_koff": -3.0}, quality="exotic")
    with pytest.raises(DegenerateBeliefError):
        b.observe(MODEL_V1, ScientificAction(action_type=A.MEASURE_SPR, candidate_id="binder-000"), impossible)
    assert np.array_equal(b.particles, before[0]) and np.array_equal(b.log_weights, before[1]) and not b.evidence


def test_tempered_updates_are_seeded_and_reproducible():
    runs = [replay(GREEDY[:4], 256, 5)[0].particles.copy() for _ in range(2)]
    assert np.array_equal(runs[0], runs[1])
    assert not np.array_equal(runs[0], replay(GREEDY[:4], 256, 6)[0].particles)
