"""Resample-move: diversity is restored without biasing the posterior."""

import numpy as np
import pytest
from binder_support import MODEL, SCHEMA, act, make_belief, obs

from mirage.belief import IndependentPrior, MixturePrior, ConditionedPrior, ParticleBelief, bernoulli, uniform
from mirage.core.contracts import ActionType as A


def distinct(b):
    return len({tuple(r) for r in b.particles})


def grid_posterior(ys, sigma=0.08):
    """Exact posterior of monomer_fraction ~ U(0.4, 1) given SEC readings ys."""
    g = np.linspace(0.4, 1.0, 20001)
    logp = sum(-0.5 * ((y - g) / sigma) ** 2 for y in ys)
    w = np.exp(logp - logp.max()); w /= w.sum()
    mean = (w * g).sum()
    return mean, np.sqrt((w * (g - mean) ** 2).sum())


@pytest.mark.parametrize("ys", [[0.7], [0.7, 0.72, 0.68, 0.71], [0.97, 0.95]])
def test_moves_preserve_the_exact_posterior(ys):
    means, stds = [], []
    for seed in range(4):
        b = make_belief(2000, seed=seed)
        for y in ys:
            info = b.observe(MODEL, act(A.MEASURE_SEC), obs(A.MEASURE_SEC, monomer_fraction=y), resample=True)
            assert info.rejuvenated
        x = b.particles[:, SCHEMA.index("monomer_fraction")]
        means.append(x.mean()); stds.append(x.std())
    m, s = grid_posterior(ys)
    assert np.mean(means) == pytest.approx(m, abs=0.01)
    assert np.mean(stds) == pytest.approx(s, rel=0.15)


def test_moves_restore_diversity_that_plain_resampling_loses():
    plan = [(A.MEASURE_SPR, dict(log_kd=-9.0, log_koff=-1.2)), (A.MEASURE_STABILITY, dict(stability_proxy=0.8)),
            (A.MEASURE_DEVELOPABILITY, dict(liability_proxy=0.2)), (A.MEASURE_SEC, dict(monomer_fraction=0.6))]
    plain, moved = make_belief(1024, rejuvenation_sweeps=0), make_belief(1024)
    for b in (plain, moved):
        for a, m in plan:
            b.observe(MODEL, act(a), obs(a, **m))
    assert distinct(plain) < 100
    assert distinct(moved) > 900


def test_beliefs_agree_across_seeds_with_moves_but_not_without():
    # Evidence well away from every failure threshold: aggregated sample (degraded SPR, low SEC).
    plan = [(A.MEASURE_SPR, "degraded", dict(log_kd=-8.15, log_koff=-0.85)),
            (A.MEASURE_STABILITY, "nominal", dict(stability_proxy=0.8)),
            (A.MEASURE_DEVELOPABILITY, "nominal", dict(liability_proxy=0.2)),
            (A.VALIDATE_ASSAY, "nominal", dict(control_signal=0.86)),
            (A.MEASURE_SEC, "nominal", dict(monomer_fraction=0.35)),
            (A.MEASURE_EPITOPE, "nominal", dict(epitope_signal=0.82))]

    def spread(sweeps):
        rows = []
        for seed in range(4):
            b = make_belief(1024, seed=seed, rejuvenation_sweeps=sweeps)
            for a, q, m in plan:
                b.observe(MODEL, act(a), obs(a, quality=q, **m))
            s = b.summary()
            rows.append([s.p_aggregation_failure, s.p_kinetic_failure, s.p_assay_invalid, s.p_epitope_failure])
        return np.array(rows).std(axis=0).max()

    assert spread(2) < 0.05
    assert spread(0) > 0.2


def test_rejuvenation_is_seeded_and_reports_acceptance():
    def run():
        b = make_belief(256, seed=3)
        info = b.observe(MODEL, act(A.MEASURE_SEC), obs(A.MEASURE_SEC, monomer_fraction=0.6), resample=True)
        return b.particles.copy(), info

    (p1, i1), (p2, i2) = run(), run()
    assert np.array_equal(p1, p2) and i1 == i2
    assert 0.0 < i1.move_acceptance <= 1.0


def test_no_moves_when_not_triggered_by_resampling():
    b = make_belief(256, ess_threshold=0.0)
    info = b.observe(MODEL, act(A.MEASURE_SEC), obs(A.MEASURE_SEC, monomer_fraction=0.6))
    assert not info.resampled and not info.rejuvenated and info.move_acceptance is None


def test_moves_disabled_without_prior_density_after_raw_update_and_after_redesign():
    no_density = IndependentPrior(SCHEMA, {f: (lambda r, n: r.uniform(0.5, 0.9, n)) for f in SCHEMA.factors})
    b = ParticleBelief.from_prior(SCHEMA, no_density, n=128)
    assert not b.can_rejuvenate
    assert not b.observe(MODEL, act(A.MEASURE_STABILITY), obs(A.MEASURE_STABILITY, stability_proxy=0.7), resample=True).rejuvenated

    raw = make_belief(128)
    raw.update(np.zeros(128))
    assert not raw.can_rejuvenate

    red = make_belief(128)
    red.observe(MODEL, act(A.MEASURE_SEC), obs(A.MEASURE_SEC, monomer_fraction=0.6), resample=True)
    assert red.can_rejuvenate
    red.apply_redesign(MODEL, act(A.REDESIGN_SOLUBILITY))
    assert not red.can_rejuvenate  # child prior is the transported cloud: density intractable
    info = red.observe(MODEL, act(A.MEASURE_SEC), obs(A.MEASURE_SEC, monomer_fraction=0.9), resample=True)
    assert info.resampled and not info.rejuvenated


def test_zero_sweeps_disables_moves():
    assert not make_belief(64, rejuvenation_sweeps=0).can_rejuvenate


def test_copy_does_not_share_evidence_or_state():
    b = make_belief(128)
    b.observe(MODEL, act(A.MEASURE_SEC), obs(A.MEASURE_SEC, monomer_fraction=0.6), resample=True)
    c = b.copy()
    c.observe(MODEL, act(A.MEASURE_STABILITY), obs(A.MEASURE_STABILITY, stability_proxy=0.7), resample=True)
    assert len(b._evidence) == 1 and len(c._evidence) == 2
    assert not np.array_equal(b.particles, c.particles)


# --- priors ----------------------------------------------------------------

def test_prior_densities():
    u, bern = uniform(0, 2), bernoulli(0.25)
    assert u.log_prob(np.array([1.0, 3.0])).tolist() == [pytest.approx(-np.log(2)), -np.inf]
    assert bern.log_prob(np.array([1.0, 0.0, 0.5])).tolist() == [pytest.approx(np.log(0.25)), pytest.approx(np.log(0.75)), -np.inf]
    assert bernoulli(1.0).log_prob(np.array([0.0, 1.0])).tolist() == [-np.inf, 0.0]


def test_mixture_and_conditioned_density_and_sampling():
    from binder_support import _GOOD, _PRIOR, _any_failure
    mix = MixturePrior([(0.5, _PRIOR), (0.5, _GOOD)])
    z = mix.sample(np.random.default_rng(0), 200)
    assert z.shape == (200, SCHEMA.dim)
    expected = np.logaddexp(np.log(0.5) + _PRIOR.log_prob(z), np.log(0.5) + _GOOD.log_prob(z))
    assert np.allclose(mix.log_prob(z), expected)
    cond = ConditionedPrior(mix, _any_failure)
    zc = cond.sample(np.random.default_rng(0), 100)
    assert _any_failure(zc).all()
    lp = cond.log_prob(z)
    assert np.all(np.isneginf(lp[~_any_failure(z)])) and np.all(np.isfinite(lp[_any_failure(z)]))


def test_independent_prior_without_densities_has_no_log_prob():
    assert not hasattr(IndependentPrior(SCHEMA, {f: (lambda r, n: np.zeros(n)) for f in SCHEMA.factors}), "log_prob")
    with pytest.raises(ValueError):
        IndependentPrior(SCHEMA, {"stability": uniform(0, 1)})


def test_binary_factors_without_evidence_keep_their_prior_marginal_after_moves():
    """Regression: an always-flip proposal left unobserved binary factors stuck on the ancestors."""
    means = []
    for seed in range(6):
        b = make_belief(1024, seed=seed)
        b.observe(MODEL, act(A.MEASURE_SPR), obs(A.MEASURE_SPR, quality="degraded", log_kd=-8.15, log_koff=-0.85))
        b.observe(MODEL, act(A.MEASURE_STABILITY), obs(A.MEASURE_STABILITY, stability_proxy=0.8), resample=True)
        means.append([b.particles[:, b.schema.index(f)].mean() for f in ("functional_epitope", "model_valid")])
    assert np.mean(means, axis=0) == pytest.approx([0.5, 0.5], abs=0.1)
    assert np.min(means) > 0.3 and np.max(means) < 0.7
