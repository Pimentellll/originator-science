import numpy as np
import pytest

from mirage.belief import (
    BINDER_SCHEMA_PROVISIONAL as SCHEMA,
    DegenerateBeliefError,
    FAILURE_FIELDS,
    IndependentPrior,
    ParticleBelief,
    stratified_resample,
    systematic_resample,
)

# Test-only prior over the schema's factors; not an environment prior.
PRIOR = IndependentPrior(
    SCHEMA,
    {
        "stability": lambda r, n: r.uniform(0, 1, n),
        "monomer_fraction": lambda r, n: r.uniform(0.4, 1, n),
        "log_kd": lambda r, n: r.uniform(-10, -5, n),
        "log_koff": lambda r, n: r.uniform(-5, 0, n),
        "functional_epitope": lambda r, n: r.uniform(0, 1, n),
        "liability": lambda r, n: r.uniform(0, 1, n),
        "assay_validity": lambda r, n: r.integers(0, 2, n).astype(float),
        "model_validity": lambda r, n: r.integers(0, 2, n).astype(float),
    },
)


def make(n=512, seed=1, **kw):
    return ParticleBelief.from_prior(SCHEMA, PRIOR, n=n, seed=seed, **kw)


def test_initial_weights_uniform_and_sum_to_one():
    b = make(256)
    assert b.weights.sum() == pytest.approx(1.0)
    assert np.allclose(b.weights, 1 / 256)
    assert b.effective_sample_size == pytest.approx(256)


def test_update_normalises_and_matches_bayes_rule():
    b = make(64, ess_threshold=0.0)
    ll = np.random.default_rng(0).normal(size=64)
    expected = np.exp(ll) / np.exp(ll).sum()
    info = b.update(ll)
    assert b.weights.sum() == pytest.approx(1.0)
    assert np.allclose(b.weights, expected)
    assert info.log_evidence == pytest.approx(np.log(np.mean(np.exp(ll))))


def test_log_weight_stability_with_extreme_loglik():
    b = make(128, ess_threshold=0.0)
    ll = np.full(128, -1e5)
    ll[7] = -1e5 + 3.0
    ll[9] = -np.inf
    b.update(ll)
    w = b.weights
    assert np.all(np.isfinite(w)) and w.sum() == pytest.approx(1.0)
    assert w[9] == 0.0 and w.argmax() == 7


def test_ess_value():
    b = make(100, ess_threshold=0.0)
    ll = np.full(100, -np.inf)
    ll[:25] = 0.0
    b.update(ll)
    assert b.effective_sample_size == pytest.approx(25.0)


def test_degenerate_evidence_raises_and_leaves_belief_unchanged():
    b = make(32)
    before = b.log_weights
    with pytest.raises(DegenerateBeliefError):
        b.update(np.full(32, -np.inf))
    assert np.array_equal(b.log_weights, before)


@pytest.mark.parametrize("bad", [np.full(31, 0.0), np.append(np.zeros(31), np.nan), np.append(np.zeros(31), np.inf)])
def test_bad_loglik_rejected(bad):
    with pytest.raises(ValueError):
        make(32).update(bad)


def test_resample_triggers_below_threshold_only():
    b = make(100, ess_threshold=0.5)
    mild = np.zeros(100); mild[:90] = -0.1
    assert not b.update(mild).resampled
    sharp = np.full(100, -np.inf); sharp[:10] = 0.0
    info = b.update(sharp)
    assert info.resampled and info.ess_weighted < 50
    assert np.allclose(b.weights, 0.01)


@pytest.mark.parametrize("scheme", ["systematic", "stratified"])
def test_resampling_reproducible_and_seed_sensitive(scheme):
    ll = np.random.default_rng(3).normal(size=200) * 3

    def run(seed):
        b = make(200, seed=5, resampling=scheme)
        b._rng = np.random.default_rng(seed)
        b.update(ll, resample=True)
        return b.particles.copy()

    assert np.array_equal(run(11), run(11))
    assert not np.array_equal(run(11), run(12))


@pytest.mark.parametrize("fn", [systematic_resample, stratified_resample])
def test_resamplers_are_unbiased_in_counts(fn):
    w = np.array([0.5, 0.25, 0.25, 0.0])
    counts = np.zeros(4)
    rng = np.random.default_rng(0)
    for _ in range(400):
        counts += np.bincount(fn(w, rng, size=40), minlength=4)
    assert counts[3] == 0
    assert counts / counts.sum() == pytest.approx(w, abs=0.01)


def test_same_seed_same_belief_trajectory():
    ll = np.random.default_rng(9).normal(size=128) * 4
    a, b = make(128, seed=3), make(128, seed=3)
    for belief in (a, b):
        belief.update(ll); belief.update(-ll)
    assert np.array_equal(a.particles, b.particles) and np.array_equal(a.log_weights, b.log_weights)


def test_copy_is_independent_and_preserves_rng():
    b = make(64, seed=2)
    c = b.copy()
    ll = np.random.default_rng(1).normal(size=64) * 5
    c.update(ll, resample=True)
    assert np.allclose(b.weights, 1 / 64)
    d = b.copy()
    d.update(ll, resample=True)
    assert np.array_equal(c.particles, d.particles)  # identical RNG state


def test_particles_view_is_read_only():
    with pytest.raises(ValueError):
        make(8).particles[0, 0] = 99.0


def test_compound_failures_survive_in_marginals():
    """High aggregation AND high kinetic failure at once; marginals need not sum to 1."""
    n = 400
    p = PRIOR.sample(np.random.default_rng(0), n)
    p[:, SCHEMA.index("monomer_fraction")] = 0.5   # aggregated
    p[:, SCHEMA.index("log_koff")] = -1.0          # fast dissociation
    p[:, SCHEMA.index("log_kd")] = -9.0            # strong affinity
    p[:, SCHEMA.index("assay_validity")] = 1.0
    p[:, SCHEMA.index("model_validity")] = 1.0
    s = ParticleBelief(SCHEMA, p).summary()
    assert s.p_aggregation_failure > 0.99 and s.p_kinetic_failure > 0.99
    assert s.p_affinity_failure < 0.01
    probs = [getattr(s, f) for f in FAILURE_FIELDS]
    assert sum(probs) > 1.5


def test_pattern_entropy_distinguishes_compound_from_independent():
    # perfectly correlated failures: 2 patterns, entropy log 2
    n = 1000
    p = PRIOR.sample(np.random.default_rng(0), n)
    bad = np.arange(n) < n // 2
    p[:, SCHEMA.index("monomer_fraction")] = np.where(bad, 0.5, 0.95)
    p[:, SCHEMA.index("log_koff")] = np.where(bad, -1.0, -4.0)
    for f, v in [("stability", 0.9), ("log_kd", -9.0), ("functional_epitope", 0.9),
                 ("liability", 0.1), ("assay_validity", 1.0), ("model_validity", 1.0)]:
        p[:, SCHEMA.index(f)] = v
    s = ParticleBelief(SCHEMA, p).summary()
    assert s.posterior_entropy == pytest.approx(np.log(2))
    assert s.p_aggregation_failure == pytest.approx(0.5) and s.p_kinetic_failure == pytest.approx(0.5)


def test_summary_fields_and_no_particle_leak():
    s = make(64).summary()
    dumped = s.model_dump()
    assert set(FAILURE_FIELDS) <= set(dumped)
    assert {"posterior_entropy", "continuous_means", "continuous_variances", "effective_sample_size"} <= set(dumped)
    assert set(dumped) == set(FAILURE_FIELDS) | {
        "posterior_entropy", "continuous_means", "continuous_variances", "effective_sample_size"}
    assert set(s.continuous_means) == set(SCHEMA.summary_factors)
    assert all(v >= 0 for v in s.continuous_variances.values())
    assert 0 <= s.posterior_entropy <= 8 * np.log(2)
    with pytest.raises(Exception):
        s.p_folding_failure = 0.0  # frozen


def test_summary_means_track_weights():
    b = make(200, ess_threshold=0.0)
    x = b.particles[:, SCHEMA.index("log_kd")]
    b.update(np.where(x > -7.5, 0.0, -np.inf))
    assert b.summary().continuous_means["log_kd"] > -7.5
    assert b.summary().continuous_variances["log_kd"] < make(200).summary().continuous_variances["log_kd"]


def test_transition_replaces_latents_with_new_candidate_beliefs():
    b = make(300, ess_threshold=0.0)
    b.update(np.where(b.particles[:, SCHEMA.index("monomer_fraction")] < 0.7, 0.0, -np.inf))
    before = b.summary().p_aggregation_failure
    old = b.particles.copy()
    w_old = b.weights

    def solubility_kernel(z, rng):  # test-only toy kernel
        z = z.copy()
        i = SCHEMA.index("monomer_fraction")
        z[:, i] = np.clip(z[:, i] + rng.normal(0.25, 0.05, len(z)), 0, 1)
        return z

    b.transition(solubility_kernel)
    assert not np.array_equal(b.particles, old)
    assert np.allclose(b.weights, w_old)
    assert b.summary().p_aggregation_failure < before
    assert 0 < b.summary().p_aggregation_failure  # uncertainty remains


def test_transition_rejects_bad_kernel():
    with pytest.raises(ValueError):
        make(16).transition(lambda z, r: z[:5])
    with pytest.raises(ValueError):
        make(16).transition(lambda z, r: z * np.nan)


def test_schema_validation():
    from dataclasses import replace
    from mirage.belief import FailureRule, LatentSchema
    rules = dict(SCHEMA.failure_rules)
    with pytest.raises(ValueError):
        LatentSchema(SCHEMA.factors, {k: v for k, v in rules.items() if k != "p_folding_failure"}, ())
    rules["p_folding_failure"] = FailureRule("nonexistent", "below", 0.0)
    with pytest.raises(ValueError):
        LatentSchema(SCHEMA.factors, rules, ())
