"""Harness: identical seeded worlds, public-only policy inputs, exploit invariants.

Worlds here come from a TEST DOUBLE (StubLabEnv); real procedural scenarios arrive from
core. Nothing below is a benchmark result.
"""

import pytest

from campaign_support import StubLabEnv, make_belief
from mirage.core import ActionType as A
from mirage.core import AgentState, ScientificAction
from mirage.evaluation.campaign import EvaluationStore, FailureLabels, PairingError
from mirage.evaluation.campaign.adversarial import EXPLOIT_POLICIES, check_exploit_invariants
from mirage.evaluation.campaign.harness import (
    Archetype,
    PolicySpec,
    SeedSplit,
    World,
    run_benchmark,
)
from mirage.provenance import PublicRecordStore, Replay


class StubOracle:
    def __init__(self, env):
        self._aggregated = bool(env._simulator_truth["aggregated"])

    def failure_labels(self, candidate_id):
        return FailureLabels(aggregation_failure=self._aggregated)

    def scenario_class(self):
        return "STUB"


class StubSource:
    def worlds(self, archetype, seeds):
        return [
            World(
                seed=s,
                archetype=archetype.value,
                scenario_class="COMPOUND_FAILURE" if archetype == Archetype.AGGREGATION_KINETIC_DEFECT else "SINGLE_FAILURE",
                regime="path_dependent" if archetype == Archetype.AGGREGATION_KINETIC_DEFECT else "myopic",
                make_env=StubLabEnv,
                make_oracle=StubOracle,
            )
            for s in seeds
        ]


class FlatBelief:
    def __init__(self):
        self.updates = 0

    def summary(self):
        return make_belief()

    def update(self, action, result):
        self.updates += 1


def belief_factory(seed, state):
    return FlatBelief()


class SecThenAbstain:
    name = "sec_then_abstain"

    def reset(self, seed=None):
        self.n = 0

    def choose_action(self, state, belief, available_actions):
        self.n += 1
        want = A.MEASURE_SEC if self.n == 1 else A.MEASURE_STABILITY if self.n == 2 else A.ABSTAIN
        return next(a for a in available_actions if a.action_type == want)


def specs():
    return {
        "sec_then_abstain": PolicySpec(SecThenAbstain, {"variant": "test"}),
        **{n: PolicySpec(f) for n, f in EXPLOIT_POLICIES.items()},
    }


def run(**overrides):
    kwargs = dict(
        benchmark_id="bm", source=StubSource(), archetypes=[Archetype.INSTABILITY, Archetype.AGGREGATION_KINETIC_DEFECT],
        seeds=[11, 12, 13], split="development", policies=specs(), belief_factory=belief_factory,
        environment_id="stub", code_version="t", scenario_version="stub/0",
    )
    kwargs.update(overrides)
    return run_benchmark(**kwargs)


def test_every_policy_plays_every_world_once():
    result = run()
    assert len(result.evaluations) == 2 * 3 * len(specs())
    pairs = {(e.policy_name, e.seed, e.scenario_class) for e in result.evaluations}
    assert len(pairs) == len(result.evaluations)
    assert result.summary.seeds == (11, 12, 13)
    assert set(result.manifest.world_fingerprints) == {f"{a}/{s}" for a in ("instability", "aggregation_kinetic_defect") for s in (11, 12, 13)}


def test_regimes_are_reported_separately():
    result = run()
    summary = result.summary.policies["sec_then_abstain"]
    assert set(summary.by_regime) == {"myopic", "path_dependent"}
    assert set(summary.by_scenario_class) == {"SINGLE_FAILURE", "COMPOUND_FAILURE"}
    assert summary.by_regime["myopic"].n_episodes == 3


def test_exploit_policies_are_never_justified():
    result = run()
    assert check_exploit_invariants(result.evaluations) == []
    flags = {e.policy_name: set(e.exploitation_flags) for e in result.evaluations}
    assert "blind_decision" in flags["exploit_blind_select"]
    assert "proxy_exploitation" in flags["exploit_proxy_chaser"]
    assert "information_gain_farming" in flags["exploit_information_farmer"]


def test_run_is_deterministic():
    a, b = run(), run()
    assert [r.digest() for r in a.records] == [r.digest() for r in b.records]
    assert a.summary == b.summary


def test_persistence_and_replay_from_disk(tmp_path):
    public, priv = PublicRecordStore(tmp_path / "pub"), EvaluationStore(tmp_path / "priv")
    result = run(record_store=public, evaluation_store=priv)
    assert len(public.list_ids()) == len(result.records)
    record = public.load(public.list_ids()[0])
    assert len(Replay(record)) == len(record.events)
    assert priv.list_summaries() == ["bm"]
    manifest = (tmp_path / "priv" / "manifests" / "bm.json").read_text()
    assert '"split": "development"' in manifest and "world_fingerprints" in manifest
    for path in (tmp_path / "pub").glob("*.jsonl"):
        assert "_simulator_truth" not in path.read_text() and "aggregated" not in path.read_text()


def test_policies_receive_only_public_objects():
    seen = []

    class Spy:
        name = "spy"

        def reset(self, seed=None):
            pass

        def choose_action(self, state, belief, available_actions):
            seen.append((state, belief, available_actions))
            return next(a for a in available_actions if a.action_type == A.ABSTAIN)

    run(policies={"spy": PolicySpec(Spy)}, archetypes=[Archetype.INSTABILITY], seeds=[1])
    state, belief, available = seen[0]
    assert isinstance(state, AgentState)
    assert all(isinstance(a, ScientificAction) for a in available)
    for obj in (state, belief, *available):
        assert not hasattr(obj, "_simulator_truth") and not hasattr(obj, "env")


def test_world_mismatch_between_policies_is_refused():
    class Drifting(StubLabEnv):
        calls = 0

        def reset(self, seed=None):
            state = super().reset(seed)
            Drifting.calls += 1
            if Drifting.calls % 2 == 0:  # the second policy would see a different world
                state = state.model_copy(update={"resources": state.resources.model_copy(update={"budget_remaining": 1.0})})
                self._state = state
            return state

    class DriftSource(StubSource):
        def worlds(self, archetype, seeds):
            return [World(s, archetype.value, "X", "myopic", Drifting, StubOracle) for s in seeds]

    with pytest.raises(PairingError):
        run(source=DriftSource(), archetypes=[Archetype.INSTABILITY], seeds=[1])


def test_wrong_seed_set_from_source_is_refused():
    class Wrong(StubSource):
        def worlds(self, archetype, seeds):
            return super().worlds(archetype, [s + 1 for s in seeds])

    with pytest.raises(PairingError):
        run(source=Wrong())


def test_policy_failures_become_incidents_not_crashes():
    class Crashes:
        name = "crashes"

        def reset(self, seed=None):
            pass

        def choose_action(self, *a):
            raise RuntimeError("boom with secret _simulator_truth")

    class Cheats(Crashes):
        def choose_action(self, state, belief, available_actions):
            return ScientificAction(action_type=A.SELECT, candidate_id="not-a-candidate")

    result = run(
        policies={"crashes": PolicySpec(Crashes), "cheats": PolicySpec(Cheats)},
        archetypes=[Archetype.INSTABILITY], seeds=[1], max_steps=5,
    )
    kinds = {i.policy_name: i.kind for i in result.manifest.incidents}
    assert kinds == {"crashes": "policy_error", "cheats": "illegal_action"}
    assert all(not e.terminated and not e.justified for e in result.evaluations)
    assert "boom" not in result.manifest.model_dump_json()


def test_environment_step_rejection_is_an_incident():
    class Selects:
        name = "selects"

        def reset(self, seed=None):
            pass

        def choose_action(self, state, belief, available_actions):
            return available_actions[0]

    result = run(source=RejectingSource_(), policies={"p": PolicySpec(Selects)}, archetypes=[Archetype.INSTABILITY], seeds=[1])
    assert result.manifest.incidents[0].kind == "step_error"
    assert "_simulator_truth" not in result.manifest.model_dump_json()


class RejectedByEnv_(StubLabEnv):
    def step(self, action):
        raise ValueError("env internals _simulator_truth")


class RejectingSource_(StubSource):
    def worlds(self, archetype, seeds):
        return [World(s, archetype.value, "X", "myopic", RejectedByEnv_, StubOracle) for s in seeds]


def test_max_steps_incident():
    class Slow:
        name = "slow"

        def reset(self, seed=None):
            pass

        def choose_action(self, state, belief, available_actions):
            return next(a for a in available_actions if a.action_type == A.MEASURE_STABILITY)

    result = run(policies={"slow": PolicySpec(Slow)}, archetypes=[Archetype.INSTABILITY], seeds=[1], max_steps=2)
    assert result.manifest.incidents[0].kind == "max_steps"


def test_seed_split_disjointness():
    SeedSplit(development=(1, 2), held_out=(3, 4)).seeds("held_out")
    with pytest.raises(ValueError):
        SeedSplit(development=(1, 2), held_out=(2, 3))
    with pytest.raises(ValueError):
        SeedSplit(development=(1, 1), held_out=(3,))
    with pytest.raises(ValueError):
        SeedSplit(development=(1,), held_out=(2,)).seeds("test")
