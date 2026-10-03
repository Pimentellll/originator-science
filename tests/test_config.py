import ast
import inspect
import json
import math
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from mirage import config
from mirage.biology.conditions import Condition, k_from_condition
from mirage.config import (
    EpisodeConfig,
    ScenarioPrior,
    canonical_sha256,
    load_demo_pair,
    load_prior,
    sample_episode,
)

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "experiments" / "configs" / "scenario_v1.json"
DEMO = ROOT / "experiments" / "configs" / "demo_pair.json"
BP, MA = Condition.BIOLOGICAL_PLATEAU, Condition.MEASUREMENT_ARTIFACT


@pytest.fixture(scope="module")
def prior() -> ScenarioPrior:
    return load_prior(SCENARIO)


def test_scenario_v1_values_match_design_5_8(prior: ScenarioPrior) -> None:
    assert prior.s_odeq_loguniform == (0.5, 2.0)
    assert prior.r_per_h_uniform == (0.6, 0.9)
    assert prior.x0_odeq_loguniform == (0.005, 0.02)
    assert prior.kappa_uniform == (0.80, 0.90)
    assert prior.lambda_uniform == (3.0, 5.0)
    assert (prior.nu, prior.n) == (8, 8)
    assert (prior.sigma_abs, prior.sigma_rel, prior.resolution) == (0.003, 0.02, 0.0001)
    assert (prior.eps_lin, prior.y_loq) == (0.05, 0.03)
    assert prior.passive_times_h == list(range(19))
    assert prior.max_time_h == 18
    assert prior.dilution_range == (1, 100)
    assert (prior.max_replicates, prior.budget_units, prior.max_turns) == (3, 6, 12)
    assert prior.plateau_fraction == 0.95
    assert prior.late_window_h == (12, 18)


def test_limits_agree_with_visible_tools_constants(prior: ScenarioPrior) -> None:
    tools = pytest.importorskip(
        "mirage.lab.tools", reason="enabled once DEV-007a is merged into wip/integration"
    )
    assert prior.max_time_h == tools.MAX_TIME_H
    assert prior.dilution_range[1] == tools.MAX_DILUTION
    assert prior.max_replicates == tools.MAX_REPLICATES
    assert prior.budget_units == tools.BUDGET_UNITS
    assert prior.max_turns == tools.MAX_TURNS


def test_invalid_json_raises(tmp_path: Path) -> None:
    bad = tmp_path / "s.json"
    bad.write_text('{"scenario_version": "scenario-v1",', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_prior(bad)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(scenario_version="scenario-v2"),
        lambda d: d.update(extra_field=1),
        lambda d: d.pop("nu"),
        lambda d: d.update(kappa_uniform=[0.9, 0.8]),
        lambda d: d.update(s_odeq_loguniform=[0.5, float("inf")]),
    ],
)
def test_schema_violation_raises(tmp_path: Path, mutate) -> None:
    data = json.loads(SCENARIO.read_text(encoding="utf-8"))
    mutate(data)
    p = tmp_path / "s.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_prior(p)


def test_canonical_hash_ignores_formatting_but_not_values(
    prior: ScenarioPrior, tmp_path: Path
) -> None:
    data = json.loads(SCENARIO.read_text(encoding="utf-8"))
    p = tmp_path / "reformatted.json"
    p.write_text(json.dumps(dict(reversed(list(data.items()))), indent=7), encoding="utf-8")
    assert canonical_sha256(load_prior(p)) == canonical_sha256(prior)
    data["kappa_uniform"] = [0.80, 0.91]
    p.write_text(json.dumps(data), encoding="utf-8")
    assert canonical_sha256(load_prior(p)) != canonical_sha256(prior)


def test_episode_config_contents(prior: ScenarioPrior) -> None:
    e = sample_episode(prior, 500004, "BIOLOGICAL_PLATEAU")
    assert isinstance(e, EpisodeConfig)
    assert e.episode_id == "s500004-BP" and e.seed == 500004 and e.condition is BP
    assert e.scenario_version == "scenario-v1"
    assert e.scenario_sha256 == canonical_sha256(prior)
    assert e.growth.k_odeq == pytest.approx(e.k_ratio * e.assay.s_odeq, rel=1e-15)
    assert sample_episode(prior, 500004, MA).episode_id == "s500004-MA"
    with pytest.raises(ValueError):
        sample_episode(prior, 1, "SOMETHING_ELSE")


def test_sampling_order_matches_design_6(prior: ScenarioPrior) -> None:
    # Independent re-derivation from the stream: u_S, u_r, u_X0, u_K in that order.
    seed = 42
    u = np.random.default_rng(np.random.SeedSequence([seed, 0])).random(4)
    for cond, (lo, hi) in ((BP, (0.80, 0.90)), (MA, (3.0, 5.0))):
        e = sample_episode(prior, seed, cond)
        assert e.assay.s_odeq == pytest.approx(0.5 * 4.0 ** u[0], rel=1e-14)
        assert e.growth.r_per_h == pytest.approx(0.6 + 0.3 * u[1], rel=1e-14)
        assert e.growth.x0_odeq == pytest.approx(0.005 * 4.0 ** u[2], rel=1e-14)
        assert e.k_ratio == pytest.approx(lo + (hi - lo) * u[3], rel=1e-14)


def test_sampling_is_deterministic(prior: ScenarioPrior) -> None:
    assert sample_episode(prior, 123, MA) == sample_episode(prior, 123, MA)
    assert sample_episode(prior, 123, MA) != sample_episode(prior, 124, MA)


def test_t024_same_seed_same_nuisance(prior: ScenarioPrior) -> None:
    for seed in range(1000):
        bp = sample_episode(prior, seed, BP)
        ma = sample_episode(prior, seed, MA)
        assert bp.assay == ma.assay
        assert (bp.growth.r_per_h, bp.growth.x0_odeq, bp.growth.nu) == (
            ma.growth.r_per_h, ma.growth.x0_odeq, ma.growth.nu,
        )
        assert bp.growth.k_odeq != ma.growth.k_odeq
        q_bp = (bp.k_ratio - 0.80) / 0.10
        q_ma = (ma.k_ratio - 3.0) / 2.0
        assert q_bp == pytest.approx(q_ma, abs=1e-12)


def test_t024_assay_code_path_takes_no_condition() -> None:
    od_reader = pytest.importorskip(
        "mirage.assay.od_reader", reason="enabled once DEV-004 is merged into wip/integration"
    )
    for name, fn in inspect.getmembers(od_reader, inspect.isfunction):
        if fn.__module__ == od_reader.__name__:
            assert "condition" not in inspect.signature(fn).parameters, name


def _ks(a: np.ndarray, b: np.ndarray) -> float:
    grid = np.sort(np.concatenate([a, b]))
    fa = np.searchsorted(np.sort(a), grid, side="right") / a.size
    fb = np.searchsorted(np.sort(b), grid, side="right") / b.size
    return float(np.max(np.abs(fa - fb)))


def test_t025_nuisance_independent_of_condition(prior: ScenarioPrior) -> None:
    bp = [sample_episode(prior, s, BP) for s in range(10_000)]
    ma = [sample_episode(prior, s, MA) for s in range(10_000, 20_000)]

    def col(eps, f):
        return np.array([f(e) for e in eps])

    for f in (
        lambda e: math.log(e.assay.s_odeq),
        lambda e: e.growth.r_per_h,
        lambda e: math.log(e.growth.x0_odeq),
    ):
        assert _ks(col(bp, f), col(ma, f)) <= 0.03


def test_t025_nuisance_draws_precede_condition_read() -> None:
    # Static check: in sample_episode, the RNG draw comes before any use of `condition`.
    tree = ast.parse(inspect.getsource(config.sample_episode))
    fn = tree.body[0]
    assert isinstance(fn, ast.FunctionDef)
    first_draw = first_condition = None
    for i, stmt in enumerate(fn.body):
        src = ast.unparse(stmt)
        if first_draw is None and "rng.random(" in src:
            first_draw = i
        names = {n.id for n in ast.walk(stmt) if isinstance(n, ast.Name)}
        if first_condition is None and "condition" in names:
            first_condition = i
    assert first_draw is not None and first_condition is not None
    assert first_draw < first_condition


def test_k_from_condition() -> None:
    assert k_from_condition(BP, s_odeq=2.0, u=0.5, kappa_uniform=(0.8, 0.9),
                            lambda_uniform=(3.0, 5.0)) == pytest.approx((1.7, 0.85))
    assert k_from_condition("MEASUREMENT_ARTIFACT", s_odeq=2.0, u=0.0,
                            kappa_uniform=(0.8, 0.9), lambda_uniform=(3.0, 5.0)) == (6.0, 3.0)
    with pytest.raises(ValueError):
        k_from_condition("X", s_odeq=1.0, u=0.5, kappa_uniform=(0.8, 0.9),
                         lambda_uniform=(3.0, 5.0))


def test_demo_pair_matches_design_7(prior: ScenarioPrior) -> None:
    bp, ma = load_demo_pair(DEMO, prior, seeds=(0, 1))
    assert (bp.condition, ma.condition) == (BP, MA)
    for e in (bp, ma):
        assert (e.growth.r_per_h, e.growth.x0_odeq) == (0.75, 0.01)
    assert bp.k_ratio == 0.85 and round(bp.assay.s_odeq, 4) == 1.2124
    assert round(bp.growth.k_odeq, 4) == 1.0306
    assert ma.k_ratio == 4.0 and ma.assay.s_odeq == 1.0 and ma.growth.k_odeq == 4.0

    def kprime(e: EpisodeConfig) -> float:
        n = e.assay.n
        return (e.growth.k_odeq**-n + e.assay.s_odeq**-n) ** (-1 / n)

    assert kprime(bp) == pytest.approx(kprime(ma), rel=1e-12)
    assert round(kprime(ma), 3) == 1.000
