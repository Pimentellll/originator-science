import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from mirage.assay.od_reader import response

ROOT = Path(__file__).resolve().parents[3]
CALIB_PATH = ROOT / "experiments" / "exploratory" / "calibration" / "calib.py"
CALIB_SPEC = importlib.util.spec_from_file_location("exploratory_calib", CALIB_PATH)
assert CALIB_SPEC is not None and CALIB_SPEC.loader is not None
calib = importlib.util.module_from_spec(CALIB_SPEC)
sys.modules["exploratory_calib"] = calib
CALIB_SPEC.loader.exec_module(calib)


def test_bin_index_default_edges_and_out_of_range_values() -> None:
    values = np.array([0, 0.0999, 0.1, 0.29, 0.3, 0.9, 1.0])
    assert calib.bin_index(values).tolist() == [0, 0, 1, 1, 2, 4, 4]

    for value in (-0.01, 1.01):
        with pytest.raises(ValueError):
            calib.bin_index([value])


def test_murphy_hand_example_with_distinct_values_and_default_bins() -> None:
    p = [0.2, 0.2, 0.8, 0.8]
    y = [0, 1, 1, 1]

    for edges in (None, calib.BIN_EDGES):
        result = calib.murphy(p, y, edges=edges)
        assert result["rel"] == pytest.approx(0.065)
        assert result["res"] == pytest.approx(0.0625)
        assert result["unc"] == pytest.approx(0.1875)
        assert result["brier"] == pytest.approx(0.19)
        assert result["residual"] == pytest.approx(0.0, abs=1e-12)


def test_murphy_identity_and_edge_cases() -> None:
    rng = np.random.default_rng(0)
    p = rng.random(50)
    y = rng.integers(0, 2, size=50)

    default = calib.murphy(p, y)
    assert default["brier"] == pytest.approx(
        default["rel"] - default["res"] + default["unc"] + default["residual"],
        abs=1e-12,
    )
    distinct = calib.murphy(p, y, edges=None)
    assert distinct["residual"] == pytest.approx(0.0, abs=1e-12)

    balanced = np.array([0, 1] * 2)
    perfect = calib.murphy(balanced, balanced)
    assert perfect["rel"] == pytest.approx(0.0)
    assert perfect["brier"] == pytest.approx(0.0)
    assert perfect["res"] == pytest.approx(0.25)
    assert perfect["unc"] == pytest.approx(0.25)

    constant = calib.murphy(np.full(4, 0.5), balanced)
    assert constant["rel"] == pytest.approx(0.0)
    assert constant["res"] == pytest.approx(0.0)
    assert constant["unc"] == pytest.approx(0.25)
    assert constant["brier"] == pytest.approx(0.25)


def test_ece_example_with_default_edges() -> None:
    assert calib.ece([0.2, 0.2, 0.8, 0.8], [0, 1, 1, 1]) == pytest.approx(
        0.5 * 0.3 + 0.5 * 0.2
    )


def test_log_loss_and_clipping_count() -> None:
    value, clipped = calib.log_loss([0.5], [1])
    assert value == pytest.approx(np.log(2))
    assert clipped == 0

    value, clipped = calib.log_loss([0, 1], [0, 1])
    assert value == pytest.approx(-np.log(1 - 1e-6))
    assert clipped == 2


def test_stratified_indices_resample_within_each_stratum_reproducibly() -> None:
    strata = ["BP", "MA"] * 15
    samples = calib.stratified_indices(strata, b=200, seed=1)
    assert samples.shape == (200, 30)

    bp_positions = np.flatnonzero(np.array(strata) == "BP")
    ma_positions = np.flatnonzero(np.array(strata) == "MA")
    for row in samples:
        assert np.isin(row, bp_positions).sum() == 15
        assert np.isin(row, ma_positions).sum() == 15

    assert np.array_equal(samples, calib.stratified_indices(strata, b=200, seed=1))
    assert not np.array_equal(samples, calib.stratified_indices(strata, b=200, seed=2))


def test_percentile_ci_ignores_nan_and_returns_none_when_all_nan() -> None:
    assert calib.percentile_ci([1.0, 2.0, np.nan, 3.0]) == pytest.approx(
        np.percentile([1.0, 2.0, 3.0], [2.5, 97.5])
    )
    assert calib.percentile_ci([np.nan, np.nan]) is None


def test_auroc_order_ties_and_empty_class() -> None:
    assert calib.auroc([2, 1], [True, False]) == pytest.approx(1.0)
    assert calib.auroc([1, 1], [True, False]) == pytest.approx(0.5)
    assert np.isnan(calib.auroc([1], [True]))


def test_poisson_binomial_survival_probabilities() -> None:
    assert calib.poisson_binomial_sf([0.5] * 4, 2) == pytest.approx(11 / 16)
    assert calib.poisson_binomial_sf([0.5] * 4, 0) == pytest.approx(1.0)
    assert calib.poisson_binomial_sf([1, 1, 0], 2) == pytest.approx(1.0)
    assert calib.poisson_binomial_sf([1, 1, 0], 3) == pytest.approx(0.0)


def test_assay_response_matches_od_reader() -> None:
    rng = np.random.default_rng(0)
    x = rng.uniform(0, 10, size=100)
    s = 1.3
    assert np.allclose(
        calib.assay_response(x, s, 8.0),
        response(x, s_odeq=s, n=8.0),
        rtol=1e-12,
    )


def test_late_posterior_synthetic_cases_and_grid_convergence() -> None:
    prior = json.loads((ROOT / "experiments" / "configs" / "scenario_v1.json").read_text())

    def f(x: float) -> float:
        return float(calib.assay_response(x, 1.0, 8.0))

    bp_obs = [(t, 1.0, f(0.85)) for t in range(14, 19)]
    bp_obs.extend([(18, 10.0, f(0.085))] * 2)
    bp = calib.late_posterior(bp_obs, prior)
    assert bp["p_ma"] < 1e-6

    ma_obs = [(t, 1.0, f(4.0)) for t in range(14, 19)]
    ma_obs.extend([(18, 10.0, f(0.4))] * 2)
    ma = calib.late_posterior(ma_obs, prior)
    assert ma["p_ma"] > 1 - 1e-6

    with_early_reads = [(12, 1.0, f(0.85)), (13, 1.0, f(0.85)), *bp_obs]
    dropped = calib.late_posterior(with_early_reads, prior)
    assert dropped["n_dropped"] == 2
    assert dropped["n_used"] == 7
    assert dropped["p_ma"] == pytest.approx(bp["p_ma"])

    with pytest.raises(ValueError):
        calib.late_posterior([(t, 1.0, f(0.85)) for t in range(12, 14)], prior)

    passive_bp_obs = [(t, 1.0, f(0.85)) for t in range(14, 19)]
    passive_default = calib.late_posterior(passive_bp_obs, prior)
    passive_coarse = calib.late_posterior(
        passive_bp_obs, prior, n_log_s=1000, n_ratio=100
    )
    assert passive_coarse["p_ma"] == pytest.approx(passive_default["p_ma"], abs=0.02)


def test_corrected_plateau_ratio_uses_only_late_diluted_reads() -> None:
    passive = {15: 1.0, 16: 1.0, 17: 1.0, 18: 1.0}
    reads = [
        (18, 10, 0.15),
        (18, 10, 0.13),
        (5, 2, 0.3),
        (18, 1, 1.2),
    ]
    assert calib.corrected_plateau_ratio(passive, reads) == pytest.approx(1.4)
    assert calib.corrected_plateau_ratio(passive, [(5, 2, 0.3), (18, 1, 1.2)]) is None


def test_simulate_ratio_noise_free_noisy_and_reproducible() -> None:
    latent = {t: 0.5 for t in range(15, 19)}
    design = [(18, 10.0, 2)]
    expected = float(
        10
        * calib.assay_response(0.05, 2.0, 8.0)
        / calib.assay_response(0.5, 2.0, 8.0)
    )
    noise_free = calib.simulate_ratio(
        latent,
        design,
        s_odeq=2.0,
        n=8.0,
        sigma_abs=0.0,
        sigma_rel=0.0,
        draws=100,
        seed=3,
        decimals=8,
    )
    assert np.allclose(noise_free, expected, atol=1e-6)

    noisy_kwargs = {
        "s_odeq": 2.0,
        "n": 8.0,
        "sigma_abs": 0.003,
        "sigma_rel": 0.02,
        "draws": 20_000,
        "seed": 3,
        "decimals": 4,
    }
    noisy = calib.simulate_ratio(latent, design, **noisy_kwargs)
    repeated = calib.simulate_ratio(latent, design, **noisy_kwargs)
    assert noisy.mean() == pytest.approx(expected, abs=0.01)
    assert np.array_equal(noisy, repeated)
