from pathlib import Path

import numpy as np
import pytest

from mirage.assay.od_reader import read
from mirage.biology.growth import richards
from mirage.config import load_prior, sample_episode
from mirage.evaluation.passive import (
    N_BINS,
    REFERENCE_SEEDS,
    build_reference,
    late_statistic,
    simulate_passive,
)

ROOT = Path(__file__).resolve().parents[1]
PRIOR = load_prior(ROOT / "experiments" / "configs" / "scenario_v1.json")
TEST_SEEDS = range(900_000, 900_500)  # GATE0_SPEC §7 "test" block, first 500 (T-008)


@pytest.fixture(scope="module")
def ref50k():
    return build_reference(PRIOR, REFERENCE_SEEDS[:50_000])


@pytest.mark.parametrize("cond", ["BIOLOGICAL_PLATEAU", "MEASUREMENT_ARTIFACT"])
def test_simulate_passive_matches_per_episode_path(cond) -> None:
    seeds = list(range(200))
    batch = simulate_passive(PRIOR, seeds, cond)
    for i, seed in enumerate(seeds):
        e = sample_episode(PRIOR, seed, cond)
        a = e.assay
        x = richards(np.arange(19), **e.growth.model_dump())
        rng = np.random.default_rng(np.random.SeedSequence([seed, 1]))
        y = read(x, rng, s_odeq=a.s_odeq, n=a.n, sigma_abs=a.sigma_abs, sigma_rel=a.sigma_rel)
        # Vectorised exp may differ by an ulp, which can flip a 4-dp rounding at most.
        assert np.max(np.abs(batch[i] - y)) <= 1e-4 + 1e-12


def test_late_statistic() -> None:
    y = np.zeros(19)
    y[13:19] = [1, 2, 3, 4, 5, 6]
    assert float(late_statistic(y)) == pytest.approx(np.log(3.5))
    with pytest.raises(ValueError):
        late_statistic(np.zeros(19))


def test_reference_is_deterministic_and_well_formed() -> None:
    a = build_reference(PRIOR, range(1_000_000, 1_002_000))
    b = build_reference(PRIOR, range(1_000_000, 1_002_000))
    assert np.array_equal(a.edges, b.edges) and np.array_equal(a.density_ma, b.density_ma)
    assert len(a.edges) == N_BINS + 1 and a.density_bp.shape == (N_BINS,)
    assert a.density_bp.min() > 0 and a.density_ma.min() > 0  # add-one smoothing
    assert a.density_bp.sum() == pytest.approx(1.0) and a.n_per_condition == 2000


def test_classify_and_out_of_range(ref50k) -> None:
    y = np.full(19, 1e-3)
    label, p = ref50k.classify(y)  # far below the pooled range -> first bin
    assert 0 <= p <= 1 and label in ("BIOMASS_AS_READ", "BIOMASS_ABOVE_READING")
    assert ref50k.classify(np.full(19, 1e6))[1] == ref50k.p_biomass_above_reading(np.full(19, 1e3))


def test_t008_passive_bayes_balanced_accuracy(ref50k) -> None:
    acc = []
    for cond, truth in (("BIOLOGICAL_PLATEAU", "BIOMASS_AS_READ"),
                        ("MEASUREMENT_ARTIFACT", "BIOMASS_ABOVE_READING")):
        ys = simulate_passive(PRIOR, TEST_SEEDS, cond)
        acc.append(np.mean([ref50k.classify(y)[0] == truth for y in ys]))
    balanced = float(np.mean(acc))
    assert balanced <= 0.65  # SVR-001 / G0-A threshold; not tuned
    assert balanced >= 0.45  # sanity: the classifier is not inverted
