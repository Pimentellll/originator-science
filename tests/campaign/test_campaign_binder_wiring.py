"""Real BinderBioPOMDP wiring: labels, prior support, identical worlds, determinism, boundary."""

import ast
import collections
import json
from pathlib import Path

import numpy as np
import pytest

from mirage.belief import BeliefSummary
from mirage.core import AgentState, ScientificAction
from mirage.environments.binder import SHOWCASE_SCENARIOS, BinderBioPOMDP, BinderWorldMode
from mirage.environments.binder.scenarios import sample_world
from mirage.evaluation.campaign.binder_benchmark import (
    BenchmarkConfig,
    ParticleBeliefSession,
    build_prior,
    export_showcase_replays,
    result_document,
    run_binder_benchmark,
)
from mirage.evaluation.campaign.harness import ARCHETYPE_TAGS, Archetype, PolicySpec, SeedSplit
from mirage.evaluation.campaign.privileged_binder import BinderPrivilegedOracle, LabelRules
from mirage.provenance import Replay, find_privileged_fields

RULES = LabelRules()
SRC = Path(__file__).resolve().parents[2] / "src" / "mirage"


def row(h):
    return np.array([[h.stability, h.monomer_fraction, h.log_kd, h.log_koff, float(h.functional_epitope),
                      h.developability_liability, float(h.assay_valid), float(h.model_valid)]])


# ---------------------------------------------------------------- scenarios
def test_five_canonical_scenarios_and_five_procedural_modes_are_wired():
    assert {a.value for a in Archetype} == {s.name for s in SHOWCASE_SCENARIOS}
    assert {tags[0].value for tags in ARCHETYPE_TAGS.values()} == {m.value for m in BinderWorldMode}
    for scenario in SHOWCASE_SCENARIOS:
        assert ARCHETYPE_TAGS[Archetype(scenario.name)][0].value == scenario.world_mode.value


EXPECTED_SIGNATURE = {
    "SINGLE_FAILURE": {"folding_failure"},
    "COMPOUND_FAILURE": {"aggregation_failure", "kinetic_failure"},
    "MIXED": {"aggregation_failure", "epitope_failure", "developability_failure"},
}


@pytest.mark.parametrize("mode", list(BinderWorldMode))
def test_label_rules_give_each_world_class_its_documented_signature(mode):
    seen = collections.Counter()
    for seed in range(300):
        labels = RULES.labels(sample_world(mode, np.random.default_rng(seed)))
        seen["assay"] += labels.assay_invalid
        seen["model"] += labels.model_invalid
        failures = set(labels.molecular_failures)
        if mode.value in EXPECTED_SIGNATURE:
            assert EXPECTED_SIGNATURE[mode.value] <= failures
        else:
            assert not failures  # good molecule
    if mode == BinderWorldMode.ASSAY_FAILURE:
        assert seen["assay"] == 300 and seen["model"] == 0
    elif mode == BinderWorldMode.MODEL_FAILURE:
        assert seen["model"] == 300 and seen["assay"] == 0
    else:
        assert seen["assay"] == seen["model"] == 0


def test_belief_schema_and_truth_labels_share_one_definition():
    schema = RULES.schema()
    from mirage.belief import ParticleBelief

    for mode in BinderWorldMode:
        for seed in range(50):
            h = sample_world(mode, np.random.default_rng(seed))
            ind = ParticleBelief(schema, row(h)).failure_indicators()[0]
            labels = RULES.labels(h)
            names = ["folding_failure", "aggregation_failure", "affinity_failure", "kinetic_failure",
                     "epitope_failure", "developability_failure", "assay_invalid", "model_invalid"]
            assert [bool(x) for x in ind] == [getattr(labels, n) for n in names]


def test_agent_prior_puts_density_on_every_generated_world():
    prior = build_prior(RULES)
    for mode in BinderWorldMode:
        for seed in range(150):
            assert np.isfinite(prior.log_prob(row(sample_world(mode, np.random.default_rng(seed))))[0])


def test_oracle_reads_every_candidate_including_redesigns():
    env = BinderBioPOMDP.from_showcase("instability")
    env.reset(seed=1)
    oracle = BinderPrivilegedOracle(env, RULES)
    assert oracle.failure_labels("binder-000").folding_failure
    env.step(ScientificAction(action_type="REDESIGN_STABILITY", candidate_id="binder-000"))
    assert oracle.failure_labels("binder-001")  # child candidate resolvable


def test_oracle_rejects_other_environments():
    with pytest.raises(TypeError):
        BinderPrivilegedOracle(object())  # type: ignore[arg-type]


# ----------------------------------------------------------- boundary checks
def test_privileged_accessor_is_imported_only_by_the_benchmark_layer():
    allowed = {"evaluation/campaign/binder_benchmark.py", "evaluation/campaign/privileged_binder.py"}
    offenders = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel in allowed:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module or ""] + [a.name for a in node.names] if isinstance(node, ast.ImportFrom) else [])
            if any("privileged_binder" in n for n in names):
                offenders.append(rel)
    assert offenders == []


def test_public_layers_never_import_the_environment_or_evaluator():
    for package in ("api", "provenance"):
        for path in (SRC / package).rglob("*.py"):
            text = path.read_text()
            for banned in ("mirage.environments", "privileged_binder", "mirage.evaluation.campaign.evaluator"):
                if package == "api" and banned.endswith("evaluator"):
                    continue  # the API serves BenchmarkSummary aggregates only
                assert banned not in text, f"{path.name} imports {banned}"


# ---------------------------------------------------------------- real runs
SPLIT = SeedSplit(development=(1, 2, 3), held_out=(90000, 90001))
SMALL = BenchmarkConfig(n_particles=128, eig_samples=16, max_steps=20)


@pytest.fixture(scope="module")
def run():
    return run_binder_benchmark(benchmark_id="t", split=SPLIT, split_name="held_out", per_archetype=2, config=SMALL, code_version="test")


def test_every_policy_plays_identical_worlds(run):
    assert set(run.summary.policies) == {"random", "fixed_pipeline", "greedy_eig"}
    assert len(run.evaluations) == 5 * 2 * 3
    by_world = collections.defaultdict(set)
    for r in run.records:
        by_world[(r.environment_id, r.seed, r.initial_state.model_dump_json())].add(r.policy.name)
    assert all(names == {"random", "fixed_pipeline", "greedy_eig"} for names in by_world.values())
    assert len(run.manifest.world_fingerprints) == 10


def test_regimes_reported_separately(run):
    regimes = set(run.summary.policies["greedy_eig"].by_regime)
    assert regimes == {"myopic", "path_dependent", "invalid", "adversarial"}
    assert set(run.summary.policies["greedy_eig"].by_archetype) == {a.value for a in Archetype}


def test_benchmark_is_deterministic(run):
    again = run_binder_benchmark(benchmark_id="t", split=SPLIT, split_name="held_out", per_archetype=2, config=SMALL, code_version="test")
    assert [r.digest() for r in again.records] == [r.digest() for r in run.records]
    assert again.summary == run.summary


def test_records_are_public_only_and_replay_without_models(run):
    for record in run.records:
        assert find_privileged_fields(record.model_dump(mode="json")) == []
        assert len(Replay(record)) == len(record.events)
        for event in record.events:
            for belief in (event.belief_before, event.belief_after):
                assert belief is not None  # beliefs are recorded for every real step


def test_no_policy_receives_truth_or_the_environment():
    seen = []

    class Spy:
        name = "spy"

        def reset(self, seed=None):
            pass

        def choose_action(self, state, belief, available_actions):
            seen.append((state, belief, tuple(available_actions)))
            return next(a for a in available_actions if a.action_type.value == "ABSTAIN")

    run_binder_benchmark(benchmark_id="s", split=SPLIT, split_name="held_out", per_archetype=1, config=SMALL, code_version="t",
                         archetypes=(Archetype.INSTABILITY,), extra_policies={"spy": PolicySpec(Spy)})
    state, belief, available = seen[0]
    assert type(state) is AgentState and type(belief) is BeliefSummary
    assert all(type(a) is ScientificAction for a in available)
    for obj in (state, belief):
        assert not any(k.startswith("_") for k in vars(obj))


def test_budget_exhaustion_and_terminal_handling_never_crash_a_policy_run(run):
    assert run.manifest.incidents == () or all(i.kind in {"belief_degenerate"} for i in run.manifest.incidents)


def test_result_document_and_showcase_export(run, tmp_path):
    paths, seed = export_showcase_replays(run, tmp_path)
    assert seed == 90000 and any(p.endswith(f"showcase_aggregation_kinetic_defect_seed{seed}.json") for p in paths)
    bundle = json.loads(Path(paths[0]).read_text())
    assert set(bundle["replays"]) == {"random", "fixed_pipeline", "greedy_eig"}
    assert bundle["selection_rule"] == "lowest held-out seed"
    doc = result_document(run, SMALL, replay_paths=paths)
    text = json.dumps(doc)
    assert doc["status"] == "real_run" and doc["policy_availability"]["lookahead"].startswith("not available")
    assert doc["approximate_regret"]["status"] == "not_computed"

    def keys(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                yield from keys(v)
        elif isinstance(node, list):
            for v in node:
                yield from keys(v)

    # Aggregates legitimately have "correct"/"justified" rates, so the record scanner does not
    # apply; instead assert that no per-episode or truth-derived field can appear.
    per_episode = {"true_level", "predicted_level", "failure_labels", "mech_tp", "decision_candidate_id", "public_digest", "_hidden_by_candidate"}
    assert per_episode.isdisjoint(set(keys(doc)))
    for needle in ("_hidden_by_candidate", "BinderHypothesis", "decision_candidate_id", "public_digest"):
        assert needle not in text
    assert len(doc["paired_comparisons"]) == 3


def test_belief_incidents_are_surfaced_not_hidden():
    from campaign_support import StubLabEnv
    from mirage.evaluation.campaign.harness import World, run_benchmark
    from test_campaign_harness import StubOracle  # noqa: PLC0415

    class FlakyBelief:
        incidents = ["belief_degenerate"]

        def summary(self):
            from mirage.evaluation.campaign.synthetic import make_belief
            return make_belief()

        def update(self, action, result):
            pass

    class Src:
        def worlds(self, archetype, seeds):
            return [World(s, archetype.value, "X", "myopic", StubLabEnv, StubOracle) for s in seeds]

    class Abstain:
        name = "a"

        def reset(self, seed=None):
            pass

        def choose_action(self, state, belief, available_actions):
            return next(a for a in available_actions if a.action_type.value == "ABSTAIN")

    result = run_benchmark(benchmark_id="b", source=Src(), archetypes=[Archetype.INSTABILITY], seeds=[1], split="development",
                           policies={"a": PolicySpec(Abstain)}, belief_factory=lambda s, st: FlakyBelief(),
                           environment_id="stub", code_version="t", scenario_version="x")
    assert [i.kind for i in result.manifest.incidents] == ["belief_degenerate"]


def test_session_swallows_degenerate_updates_but_records_them():
    from mirage.belief import ParticleBelief
    from mirage.belief.binder import BinderParticleModel
    from mirage.core import ScientificObservation, StepResult

    schema = RULES.schema()
    belief = ParticleBelief.from_prior(schema, build_prior(RULES), n=64, seed=0)
    session = ParticleBeliefSession(belief, BinderParticleModel(schema=schema))
    env = BinderBioPOMDP.from_showcase("instability")
    state = env.reset(seed=0)
    impossible = ScientificObservation(action_type="MEASURE_SEC", candidate_id="binder-000",
                                       measurements={"monomer_fraction": 0.5}, quality="degraded")
    session.update(ScientificAction(action_type="MEASURE_SEC", candidate_id="binder-000"),
                   StepResult(action=ScientificAction(action_type="MEASURE_SEC", candidate_id="binder-000"),
                              observation=impossible, state=state, terminal=False))
    assert session.incidents == ["belief_degenerate"]
