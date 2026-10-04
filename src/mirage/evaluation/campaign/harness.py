"""Benchmark harness (BENCHMARK_PROTOCOL.md): identical seeded worlds for every policy.

This module is simulator-agnostic. A ``WorldSource`` supplied by the environment owner
turns (archetype, seed) into a ``World``; the harness never constructs molecular state.
Policies see only AgentState, a belief summary and the available actions.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from mirage.core import ScientificEnvironment
from mirage.evaluation.campaign.aggregate import (
    BenchmarkSummary,
    EvaluationStore,
    PairingError,
    build_benchmark_summary,
)
from mirage.evaluation.campaign.evaluator import CampaignEvaluation, CampaignEvaluator
from mirage.evaluation.campaign.truth import TruthOracle
from mirage.provenance import EpisodeRecord, EpisodeRecorder, PolicyMetadata, PublicRecordStore
from mirage.provenance.protocols import BeliefFactory, PolicyLike
from mirage.provenance.store import atomic_write_text, safe_id


class ScenarioClass(str, Enum):
    """Generation controls / reporting archetypes (SCENARIO_GENERATION.md)."""

    SINGLE_FAILURE = "SINGLE_FAILURE"
    COMPOUND_FAILURE = "COMPOUND_FAILURE"
    ASSAY_FAILURE = "ASSAY_FAILURE"
    MODEL_FAILURE = "MODEL_FAILURE"
    MIXED = "MIXED"


class Archetype(str, Enum):
    """The minimum required cases (BINDER_ENVIRONMENT.md)."""

    SIMPLE_INSTABILITY = "SIMPLE_INSTABILITY"
    AGGREGATION_KINETIC = "AGGREGATION_KINETIC"
    BROKEN_ASSAY = "BROKEN_ASSAY"
    INVALID_MODEL = "INVALID_MODEL"
    PROXY_TRAP = "PROXY_TRAP"


class Regime(str, Enum):
    """BASELINES.md: myopic, path-dependent and invalid-assay/model worlds are reported apart."""

    MYOPIC = "myopic"
    PATH_DEPENDENT = "path_dependent"
    INVALID = "invalid"
    ADVERSARIAL = "adversarial"


# Default reporting tags; the world source may override them per world.
ARCHETYPE_TAGS: dict[Archetype, tuple[ScenarioClass, Regime]] = {
    Archetype.SIMPLE_INSTABILITY: (ScenarioClass.SINGLE_FAILURE, Regime.MYOPIC),
    Archetype.AGGREGATION_KINETIC: (ScenarioClass.COMPOUND_FAILURE, Regime.PATH_DEPENDENT),
    Archetype.BROKEN_ASSAY: (ScenarioClass.ASSAY_FAILURE, Regime.INVALID),
    Archetype.INVALID_MODEL: (ScenarioClass.MODEL_FAILURE, Regime.INVALID),
    Archetype.PROXY_TRAP: (ScenarioClass.MIXED, Regime.ADVERSARIAL),
}


@dataclass(frozen=True)
class World:
    """One seeded world. ``make_env`` must return a fresh, independent environment each call;
    ``make_oracle`` receives that environment *after* play and returns the privileged labels
    accessor (the environment owner's evaluator-specific interface)."""

    seed: int
    archetype: str
    scenario_class: str
    regime: str
    make_env: Callable[[], ScientificEnvironment]
    make_oracle: Callable[[ScientificEnvironment], TruthOracle]


class WorldSource(Protocol):
    def worlds(self, archetype: Archetype, seeds: Sequence[int]) -> Sequence[World]: ...


class _TaggedOracle:
    """Applies the world's reporting tags on top of the owner's oracle."""

    def __init__(self, inner: TruthOracle, archetype: str, scenario_class: str, regime: str) -> None:
        self._inner, self._archetype = inner, archetype
        self._scenario_class, self._regime = scenario_class, regime

    def failure_labels(self, candidate_id: str):
        return self._inner.failure_labels(candidate_id)

    def scenario_class(self) -> str:
        return self._scenario_class

    def regime(self) -> str:
        return self._regime

    def archetype(self) -> str:
        return self._archetype


@dataclass(frozen=True)
class SeedSplit:
    """Development and held-out seeds must never overlap (BENCHMARK_PROTOCOL)."""

    development: tuple[int, ...]
    held_out: tuple[int, ...]

    def __post_init__(self) -> None:
        overlap = set(self.development) & set(self.held_out)
        if overlap:
            raise ValueError(f"development and held-out seeds overlap: {sorted(overlap)}")
        for name, seeds in (("development", self.development), ("held_out", self.held_out)):
            if len(seeds) != len(set(seeds)):
                raise ValueError(f"{name} seeds contain duplicates")

    def seeds(self, split: str) -> tuple[int, ...]:
        if split not in ("development", "held_out"):
            raise ValueError("split must be 'development' or 'held_out'")
        return getattr(self, split)


class Incident(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    episode_id: str
    policy_name: str
    seed: int
    kind: str  # "policy_error" | "illegal_action" | "step_error" | "max_steps"


class BenchmarkManifest(BaseModel):
    """Everything needed to attribute and repeat a run (BENCHMARK_PROTOCOL)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    benchmark_id: str
    split: str
    evaluator_version: str
    code_version: str
    environment_id: str
    scenario_version: str
    seeds: tuple[int, ...]
    archetypes: tuple[str, ...]
    policies: dict[str, dict[str, str | int | float | bool | None]]
    max_steps: int
    world_fingerprints: dict[str, str]  # "<archetype>/<seed>" -> initial public state digest
    incidents: tuple[Incident, ...]


@dataclass
class BenchmarkRun:
    manifest: BenchmarkManifest
    summary: BenchmarkSummary
    evaluations: list[CampaignEvaluation] = field(default_factory=list)
    records: list[EpisodeRecord] = field(default_factory=list)


@dataclass(frozen=True)
class PolicySpec:
    factory: Callable[[], PolicyLike]
    config: Mapping[str, str | int | float | bool | None] = field(default_factory=dict)


def _fingerprint(record: EpisodeRecord) -> str:
    import hashlib

    return hashlib.sha256(record.initial_state.model_dump_json().encode()).hexdigest()


def play_episode(
    world: World,
    spec: PolicySpec,
    policy_name: str,
    belief_factory: BeliefFactory | None,
    *,
    episode_id: str,
    max_steps: int,
    environment_id: str,
    code_version: str,
) -> tuple[EpisodeRecord, ScientificEnvironment, str | None]:
    """Run one policy on one world. Returns (public record, env for the oracle, incident kind)."""
    env = world.make_env()
    state = env.reset(seed=world.seed)
    policy = spec.factory()
    policy.reset(world.seed)
    belief = belief_factory(world.seed, state) if belief_factory else None
    recorder = EpisodeRecorder(
        episode_id=episode_id,
        seed=world.seed,
        initial_state=state,
        policy=PolicyMetadata(name=policy_name, config=dict(spec.config)),
        environment_id=environment_id,
        code_version=code_version,
    )
    incident: str | None = None
    for _ in range(max_steps):
        available = tuple(env.available_actions())
        belief_before = belief.summary() if belief else None
        try:
            action = policy.choose_action(state, belief_before, available)
        except Exception:  # a crashing policy is an incident, not a benchmark abort
            incident = "policy_error"
            break
        if action not in available:
            incident = "illegal_action"
            break
        try:
            result = env.step(action)
        except ValueError:
            incident = "step_error"
            break
        if belief:
            belief.update(action, result)
        recorder.record_step(
            state_before=state,
            action=action,
            result=result,
            belief_before=belief_before,
            belief_after=belief.summary() if belief else None,
        )
        state = result.state
        if result.terminal:
            break
    else:
        incident = "max_steps"
    return recorder.finish(), env, incident


def run_benchmark(
    *,
    benchmark_id: str,
    source: WorldSource,
    archetypes: Sequence[Archetype],
    seeds: Sequence[int],
    split: str,
    policies: Mapping[str, PolicySpec],
    belief_factory: BeliefFactory | None,
    evaluator: CampaignEvaluator | None = None,
    environment_id: str,
    code_version: str,
    scenario_version: str,
    max_steps: int = 40,
    record_store: PublicRecordStore | None = None,
    evaluation_store: EvaluationStore | None = None,
) -> BenchmarkRun:
    """Every policy plays every (archetype, seed) world; worlds must be identical across
    policies or the run is refused (G13). Results are whatever the evaluator computes;
    nothing is filled in."""
    evaluator = evaluator or CampaignEvaluator()
    if not policies:
        raise ValueError("at least one policy is required")
    evaluations: list[CampaignEvaluation] = []
    records: list[EpisodeRecord] = []
    incidents: list[Incident] = []
    fingerprints: dict[str, str] = {}
    for archetype in archetypes:
        worlds = list(source.worlds(archetype, seeds))
        if sorted(w.seed for w in worlds) != sorted(seeds):
            raise PairingError(f"world source did not return exactly the requested seeds for {archetype.value}")
        for world in worlds:
            key = f"{archetype.value}/{world.seed}"
            for name in sorted(policies):
                episode_id = f"{benchmark_id}-{archetype.value}-{world.seed}-{name}"
                record, env, incident = play_episode(
                    world,
                    policies[name],
                    name,
                    belief_factory,
                    episode_id=episode_id,
                    max_steps=max_steps,
                    environment_id=environment_id,
                    code_version=code_version,
                )
                fp = _fingerprint(record)
                if fingerprints.setdefault(key, fp) != fp:
                    raise PairingError(f"policy {name} saw a different initial world for {key}")
                if incident:
                    incidents.append(Incident(episode_id=episode_id, policy_name=name, seed=world.seed, kind=incident))
                oracle = _TaggedOracle(world.make_oracle(env), world.archetype, world.scenario_class, world.regime)
                evaluation = evaluator.evaluate(record, oracle)
                if record_store:
                    record_store.save(record)
                if evaluation_store:
                    evaluation_store.save_evaluation(evaluation)
                evaluations.append(evaluation)
                records.append(record)
    summary = build_benchmark_summary(benchmark_id, evaluations)
    if evaluation_store:
        evaluation_store.save_summary(summary)
    manifest = BenchmarkManifest(
        benchmark_id=benchmark_id,
        split=split,
        evaluator_version=evaluator.config.version,
        code_version=code_version,
        environment_id=environment_id,
        scenario_version=scenario_version,
        seeds=tuple(seeds),
        archetypes=tuple(a.value for a in archetypes),
        policies={n: dict(s.config) for n, s in sorted(policies.items())},
        max_steps=max_steps,
        world_fingerprints=fingerprints,
        incidents=tuple(incidents),
    )
    if evaluation_store:
        atomic_write_text(
            evaluation_store.root / "manifests" / f"{safe_id(benchmark_id)}.json",
            manifest.model_dump_json(indent=2) + "\n",
        )
    return BenchmarkRun(manifest=manifest, summary=summary, evaluations=evaluations, records=records)
