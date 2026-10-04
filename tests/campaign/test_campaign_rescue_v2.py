"""Binder Rescue V2 preregistration: sampler properties, world identity, lock integrity.

No policy is evaluated here. These are properties of the frozen design, not results.
"""

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from mirage.core import ActionType as A
from mirage.core import ScientificAction
from mirage.environments.binder import BinderBioPOMDP
from mirage.environments.binder.environment import _COSTS
from mirage.evaluation.campaign import rescue_v2 as r
from mirage.evaluation.campaign.harness import Archetype, PolicySpec, SeedSplit
from mirage.evaluation.campaign.privileged_binder import BinderPrivilegedOracle, world_digests

ROOT = Path(__file__).resolve().parents[2]
SEEDS = range(60000, 60050)


def test_cost_table_matches_core():
    for name, (budget, sample, time) in r.ACTION_COSTS.items():
        c = _COSTS[A(name)]
        assert (budget, sample, time) == (c.budget, c.sample, c.time)
    assert r.funnel_cost() == (8.25, 3.15)


@pytest.mark.parametrize("stratum", r.STRATUM_ORDER)
def test_draws_are_deterministic_in_range_and_rounded(stratum):
    s = r.STRATA[stratum]
    for seed in list(SEEDS) + [0, 1, 123456]:
        a, b = r.sample_resources(seed, stratum), r.sample_resources(seed, stratum)
        assert a == b
        assert s.budget[0] <= a.budget_remaining <= s.budget[1]
        assert s.sample[0] <= a.sample_remaining <= s.sample[1]
        assert s.spr_health[0] <= a.spr_instrument_health <= s.spr_health[1]
        assert a.simulated_time == 0.0
        assert round(a.budget_remaining, 2) == a.budget_remaining


def test_strata_use_distinct_independent_streams():
    low, med, high = (r.sample_resources(60000, s) for s in r.STRATUM_ORDER)
    assert len({low.budget_remaining, med.budget_remaining, high.budget_remaining}) == 3
    # a seed's resources do not predict its neighbour's (no seed-adjacent correlation)
    b = [r.sample_resources(s, "high").budget_remaining for s in range(60000, 60400)]
    assert abs(np.corrcoef(b[:-1], b[1:])[0, 1]) < 0.15


def test_low_stratum_makes_the_complete_fixed_funnel_infeasible_in_every_draw():
    fb, fs = r.funnel_cost()
    assert r.STRATA["low"].budget[1] < fb and r.STRATA["low"].sample[1] < fs
    assert r.funnel_affordable_fraction("low", n=100_000) == 0.0
    for seed in range(5000):
        res = r.sample_resources(seed, "low")
        assert res.budget_remaining < fb and res.sample_remaining < fs


def test_high_stratum_allows_the_funnel_with_room_to_spare_and_medium_is_in_between():
    fb, fs = r.funnel_cost()
    assert r.STRATA["high"].budget[0] - fb >= 1.75 and r.STRATA["high"].sample[0] - fs >= 1.85
    assert r.funnel_affordable_fraction("high", n=100_000) == 1.0
    assert 0.2 < r.funnel_affordable_fraction("medium", n=100_000) < 0.5


def test_justified_select_is_structurally_impossible_in_low_and_possible_in_high():
    low = r.select_justifiable_fraction("low", n=50_000)
    high = r.select_justifiable_fraction("high", n=50_000)
    assert all(v == 0.0 for v in low.values()) and all(v == 1.0 for v in high.values())
    cheap = r.minimal_justified_costs()["REJECT (cheapest evidenced factor)"]
    assert cheap["budget"] <= r.STRATA["low"].budget[0] and cheap["sample"] <= r.STRATA["low"].sample[0]  # LOW not degenerate


def test_time_is_documented_as_unconstrained_because_core_has_no_deadline():
    assert "simulated_time" in r.UNCONSTRAINED
    env = BinderBioPOMDP.from_showcase("instability")
    env.reset(seed=1)
    assert not hasattr(env.agent_state().resources, "time_remaining")


@pytest.mark.parametrize("archetype", [a.value for a in Archetype])
@pytest.mark.parametrize("stratum", r.STRATUM_ORDER)
def test_hidden_world_and_observation_stream_are_identical_to_the_plain_environment(archetype, stratum):
    seed = 60007
    plain = BinderBioPOMDP.from_showcase(archetype)
    plain.reset(seed=seed)
    wrapped = r.ResourceConstrainedBinder(
        next(s.world_mode for s in __import__("mirage.environments.binder", fromlist=["x"]).SHOWCASE_SCENARIOS if s.name == archetype), stratum
    )
    start = wrapped.reset(seed=seed)
    assert start.resources == r.sample_resources(seed, stratum)
    assert BinderPrivilegedOracle(plain)._hidden == BinderPrivilegedOracle(wrapped)._hidden
    for kind in (A.MEASURE_STABILITY, A.MEASURE_SEC):  # affordable in every stratum together
        action = ScientificAction(action_type=kind, candidate_id="binder-000")
        assert plain.step(action).observation == wrapped.step(action).observation


def test_v2_worlds_equal_v1_worlds_for_the_same_seed():
    a = world_digests([Archetype.INSTABILITY, Archetype.BROKEN_ASSAY], [50000, 50001])
    path = ROOT / "results" / "baseline_v1" / "world_digests.json"
    if not path.exists():
        pytest.skip("baseline_v1 artifacts not present")
    v1 = json.loads(path.read_text())["digests"]
    assert all(v1[k] == v for k, v in a.items())


def test_resource_draw_does_not_change_when_other_strata_are_requested():
    first = r.sample_resources(60001, "medium")
    for s in r.STRATUM_ORDER:
        r.sample_resources(60001, s)
    assert r.sample_resources(60001, "medium") == first


def test_seed_sets_are_disjoint_and_sized_as_preregistered():
    sets = {
        "dev": set(r.SEEDS["development"]), "held": set(r.SEEDS["held_out"]),
        "v1dev": set(r.V1_SEEDS["development"]), "v1held": set(r.V1_SEEDS["held_out"]),
    }
    names = list(sets)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            assert not sets[a] & sets[b], (a, b)
    lo, hi = r.SEEDS["train_reserved_inclusive"]
    assert not any(lo <= s <= hi for s in set().union(*sets.values()))
    assert len(sets["dev"]) == len(sets["held"]) == 50
    assert r.spec_dict()["episodes_per_policy"] == 750 and r.spec_dict()["worlds_per_stratum"] == 250
    SeedSplit(development=tuple(r.SEEDS["development"]), held_out=tuple(r.SEEDS["held_out"]))  # validates


def test_world_source_crosses_every_seed_with_every_stratum():
    from mirage.evaluation.campaign.harness import run_benchmark

    source = r.RescueWorldSource()
    worlds = source.worlds(Archetype.INSTABILITY, [60000, 60001])
    assert [w.archetype for w in worlds] == [f"instability.{s}" for _ in range(2) for s in r.STRATUM_ORDER]
    assert {w.regime for w in worlds} == set(r.STRATUM_ORDER)

    class Abstain:
        name = "abstain"

        def reset(self, seed=None):
            pass

        def choose_action(self, state, belief, available_actions):
            return next(a for a in available_actions if a.action_type == A.ABSTAIN)

    run = run_benchmark(
        benchmark_id="v2t", source=source, archetypes=[Archetype.INSTABILITY], seeds=[60000, 60001], split="held_out",
        policies={"abstain": PolicySpec(Abstain)}, belief_factory=None, environment_id="BinderBioPOMDP",
        code_version="t", scenario_version="v2", max_steps=5,
    )
    assert len(run.evaluations) == 6 and set(run.summary.policies["abstain"].by_regime) == set(r.STRATUM_ORDER)
    for record in run.records:
        stratum = record.episode_id.split(".")[-1].split("-")[0]
        assert record.initial_state.resources == r.sample_resources(record.seed, stratum)


# ------------------------------------------------------------------- lock
def test_committed_lock_matches_the_files_on_disk():
    assert r.verify_lock(ROOT) == []


def test_lock_detects_any_change_to_spec_scoring_or_doc(tmp_path):
    for rel in (*r.LOCKED_FILES, f"{r.PREREG_DIR}/PREREGISTRATION.json"):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, target)
    assert r.verify_lock(tmp_path) == []
    for rel in (
        "src/mirage/evaluation/campaign/evidence.py",
        "docs/evaluation/BINDER_RESCUE_V2.md",
        f"{r.PREREG_DIR}/spec.json",
        f"{r.PREREG_DIR}/seed_manifest.json",
    ):
        path = tmp_path / rel
        original = path.read_bytes()
        path.write_bytes(original + b"\n# edited")
        assert any(rel in p for p in r.verify_lock(tmp_path)), rel
        path.write_bytes(original)


def test_machine_readable_spec_equals_the_code_spec():
    on_disk = json.loads((ROOT / r.PREREG_DIR / "spec.json").read_text())
    assert on_disk == json.loads(json.dumps(r.spec_dict()))
    manifest = json.loads((ROOT / r.PREREG_DIR / "seed_manifest.json").read_text())
    assert manifest["held_out"] == r.SEEDS["held_out"] and manifest["development"] == r.SEEDS["development"]
