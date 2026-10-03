import ast
import hashlib
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
    from mirage.lab import tools

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
    from mirage.assay import od_reader

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


# ---- review fixes (fix/config-limits) -------------------------------------------------------

def _write(tmp_path: Path, mutate) -> Path:
    data = json.loads(SCENARIO.read_text(encoding="utf-8"))
    mutate(data)
    p = tmp_path / "s.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


@pytest.mark.parametrize("field,value", [
    ("max_time_h", 17), ("dilution_range", [1, 50]), ("dilution_range", [2, 100]),
    ("dilution_range", [0.5, 100]), ("max_replicates", 4),
    ("budget_units", 5), ("max_turns", 13)])
def test_limits_mismatch_with_tools_raises_at_load(tmp_path: Path, field, value) -> None:
    p = _write(tmp_path, lambda d: d.update({field: value}))
    with pytest.raises(ValueError, match=f"{field} .* does not match mirage.lab.tools"):
        load_prior(p)


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(s_odeq_loguniform=[-0.5, 2.0]),
    lambda d: d.update(x0_odeq_loguniform=[0.0, 0.02]),
    lambda d: d.update(x0_odeq_loguniform=[-0.02, -0.005]),
    lambda d: d.update(r_per_h_uniform=[0.6, 0.6]),
    lambda d: d.update(s_odeq_loguniform=[2.0, 2.0]),
    lambda d: d.update(passive_times_h=[]),
    lambda d: d.update(nu=-8),
    lambda d: d.update(n=-8),
    lambda d: d.update(nu=0),
    lambda d: d.update(sigma_abs=-0.003),
    lambda d: d.update(sigma_rel=-0.02),
    lambda d: d.update(resolution=-0.0001),
    lambda d: d.update(y_loq=-0.03),
    lambda d: d.update(eps_lin=1.5),
], ids=["S<0", "X0=0", "X0<0", "r-equal", "S-equal", "empty-schedule", "nu<0", "n<0", "nu=0",
        "sigma_abs<0", "sigma_rel<0", "resolution<0", "y_loq<0", "eps_lin>1"])
def test_invalid_prior_values_raise(tmp_path: Path, mutate) -> None:
    with pytest.raises(ValidationError):
        load_prior(_write(tmp_path, mutate))


@pytest.mark.parametrize("field", ["nu", "n", "sigma_abs", "sigma_rel", "eps_lin", "y_loq", "plateau_fraction"])
@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_tokens_rejected(tmp_path: Path, field, token) -> None:
    text = SCENARIO.read_text(encoding="utf-8")
    data = json.loads(text)
    text = text.replace(f'"{field}": {json.dumps(data[field])}', f'"{field}": {token}', 1)
    assert token in text
    p = tmp_path / "s.json"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(ValidationError, match="finite"):
        load_prior(p)


@pytest.mark.parametrize("field", ["nu", "n", "sigma_abs", "sigma_rel", "resolution", "eps_lin", "y_loq"])
def test_nan_values_rejected_by_schema(field, prior: ScenarioPrior) -> None:
    with pytest.raises(ValidationError):
        ScenarioPrior.model_validate({**prior.model_dump(), field: float("nan")})


@pytest.mark.parametrize("cond", [BP, MA])
def test_sampled_constants_copied_from_prior(prior: ScenarioPrior, cond) -> None:
    for seed in range(20):
        e = sample_episode(prior, seed, cond)
        assert e.growth.nu == prior.nu == 8
        assert (e.assay.n, e.assay.sigma_abs, e.assay.sigma_rel) == (8, 0.003, 0.02)
        assert (e.assay.resolution, e.assay.eps_lin, e.assay.y_loq) == (0.0001, 0.05, 0.03)


def test_episode_models_frozen_and_extra_forbidden(prior: ScenarioPrior) -> None:
    e = sample_episode(prior, 3, MA)
    for obj, field in ((e, "seed"), (e.growth, "k_odeq"), (e.assay, "s_odeq")):
        with pytest.raises(ValidationError):
            setattr(obj, field, 1.0)
    for model, obj in ((EpisodeConfig, e), (config.GrowthConfig, e.growth), (config.AssayConfig, e.assay)):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            model.model_validate({**obj.model_dump(), "leak": 1})


CANONICAL_V1 = (
    '{"budget_units":6,"dilution_range":[1.0,100.0],"eps_lin":0.05,"kappa_uniform":[0.8,0.9],'
    '"lambda_uniform":[3.0,5.0],"late_window_h":[12,18],"max_replicates":3,"max_time_h":18,'
    '"max_turns":12,"n":8.0,"nu":8.0,"passive_times_h":[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,'
    '16,17,18],"plateau_fraction":0.95,"r_per_h_uniform":[0.6,0.9],"resolution":0.0001,'
    '"s_odeq_loguniform":[0.5,2.0],"scenario_version":"scenario-v1","sigma_abs":0.003,'
    '"sigma_rel":0.02,"x0_odeq_loguniform":[0.005,0.02],"y_loq":0.03}'
)
SCENARIO_V1_SHA256 = "5291e69c061fa42973cf541bd84b78a90770dc971227f32f052acfc404c0ce08"


def test_canonical_sha256_from_specified_bytes(prior: ScenarioPrior) -> None:
    assert hashlib.sha256(CANONICAL_V1.encode("utf-8")).hexdigest() == SCENARIO_V1_SHA256
    assert canonical_sha256(prior) == SCENARIO_V1_SHA256
