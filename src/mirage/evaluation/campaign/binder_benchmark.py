"""Real Binder campaign benchmark (C2): wiring of core worlds, belief, policies and the harness.

No simulator is duplicated here. The belief prior below is the *agent-side public prior*
shared by every policy; it is a modelling assumption of this benchmark (core publishes none),
chosen broad enough to put positive density on every world the generator can produce
(verified by a test) and NOT tuned to the world mix.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from mirage.belief import (
    BeliefSummary,
    ConditionedPrior,
    DegenerateBeliefError,
    IndependentPrior,
    ParticleBelief,
    bernoulli,
    uniform,
)
from mirage.belief.binder import BinderParticleModel
from mirage.core import AgentState, ScientificAction, StepResult
from mirage.evaluation.campaign.aggregate import (
    EvaluationStore,
    PairedComparison,
    RegretEstimate,
    approximate_regret,
    paired_comparison,
)
from mirage.evaluation.campaign.harness import (
    Archetype,
    BenchmarkRun,
    PolicySpec,
    SeedSplit,
    run_benchmark,
)
from mirage.evaluation.campaign.privileged_binder import BinderWorldSource, LabelRules
from mirage.policies import FixedPipelinePolicy, GreedyEIGPolicy, RandomPolicy
from mirage.policies.base import REDESIGN_ACTIONS
from mirage.provenance import PublicRecordStore
from mirage.api.dto import replay_dto

RESULT_SCHEMA = "mirage.binder_campaign_benchmark/1"
INITIAL_BUDGET = 12.0  # core's BinderBioPOMDP reset budget; used only to normalise regret cost

# Public agent-side prior parameters (recorded in the result file).
PRIOR_PARAMS: dict[str, Any] = {
    "stability": ["uniform", 0.0, 1.0],
    "monomer_fraction": ["uniform", 0.05, 1.0],
    "log_kd": ["uniform", -10.0, -5.0],
    "log_koff": ["uniform", -5.0, 1.0],
    "functional_epitope": ["bernoulli", 0.5],
    "developability_liability": ["uniform", 0.0, 1.0],
    "assay_valid": ["bernoulli", 0.75],
    "model_valid": ["bernoulli", 0.75],
    "conditioning": "campaign starts from a downstream failure: at least one failure rule fires",
}


def build_prior(rules: LabelRules) -> ConditionedPrior:
    schema = rules.schema()
    base = IndependentPrior(
        schema,
        {
            "stability": uniform(0.0, 1.0),
            "monomer_fraction": uniform(0.05, 1.0),
            "log_kd": uniform(-10.0, -5.0),
            "log_koff": uniform(-5.0, 1.0),
            "functional_epitope": bernoulli(0.5),
            "developability_liability": uniform(0.0, 1.0),
            "assay_valid": bernoulli(0.75),
            "model_valid": bernoulli(0.75),
        },
    )
    return ConditionedPrior(base, lambda z: ParticleBelief(schema, z).failure_indicators().any(axis=1))


class ParticleBeliefSession:
    """Controller-side tracker: owns the ParticleBelief; policies only ever see its summary
    (GreedyEIG additionally gets the handle through ``belief_source``, as its contract says)."""

    def __init__(self, belief: ParticleBelief, model: BinderParticleModel) -> None:
        self.belief = belief
        self.model = model
        self.incidents: list[str] = []

    def summary(self) -> BeliefSummary:
        return self.belief.summary()

    def update(self, action: ScientificAction, result: StepResult) -> None:
        try:
            if result.observation is not None:
                self.belief.observe(self.model, action, result.observation)
            elif action.action_type in REDESIGN_ACTIONS:
                self.belief.apply_redesign(self.model, action)
        except DegenerateBeliefError:
            # The observation had zero likelihood under every particle (model misfit). The
            # belief is left unchanged and the event is reported, never hidden.
            self.incidents.append("belief_degenerate")


@dataclass(frozen=True)
class BenchmarkConfig:
    n_particles: int = 512
    eig_samples: int = 64
    max_steps: int = 24
    rules: LabelRules = LabelRules()
    decision_threshold: float = 0.5


def belief_factory(config: BenchmarkConfig):
    schema = config.rules.schema()
    prior = build_prior(config.rules)
    model = BinderParticleModel(schema=schema)

    def make(seed: int, state: AgentState) -> ParticleBeliefSession:
        # Seeded by the world only, so every policy starts from the identical belief.
        belief = ParticleBelief.from_prior(schema, prior, n=config.n_particles, seed=seed, ess_threshold=0.5)
        return ParticleBeliefSession(belief, model)

    return make, model


def policy_specs(config: BenchmarkConfig, model: BinderParticleModel) -> dict[str, PolicySpec]:
    return {
        "random": PolicySpec(RandomPolicy, {"allow_terminal": True}),
        "fixed_pipeline": PolicySpec(lambda: FixedPipelinePolicy(), {"decision_threshold": 0.5}),
        "greedy_eig": PolicySpec(
            lambda session: GreedyEIGPolicy(
                model,
                lambda: session.belief,
                n_samples=config.eig_samples,
                decision_threshold=config.decision_threshold,
            ),
            {"n_samples": config.eig_samples, "decision_threshold": config.decision_threshold, "min_eig": 0.02},
            bind=True,
        ),
    }


UNAVAILABLE_POLICIES = {
    "lookahead": "not available: LookaheadPolicy has not landed on any integrated branch",
    "ppo": "not available: no real PPO checkpoint has landed (RL work has not produced one)",
}


def run_binder_benchmark(
    *,
    benchmark_id: str,
    split: SeedSplit,
    split_name: str,
    per_archetype: int,
    archetypes: tuple[Archetype, ...] = tuple(Archetype),
    config: BenchmarkConfig = BenchmarkConfig(),
    code_version: str,
    extra_policies: Mapping[str, PolicySpec] | None = None,
    record_store: PublicRecordStore | None = None,
    evaluation_store: EvaluationStore | None = None,
) -> BenchmarkRun:
    seeds = split.seeds(split_name)[:per_archetype]
    if len(seeds) < per_archetype:
        raise ValueError(f"split {split_name} has only {len(seeds)} seeds, need {per_archetype}")
    make_belief, model = belief_factory(config)
    policies = {**policy_specs(config, model), **(extra_policies or {})}
    return run_benchmark(
        benchmark_id=benchmark_id,
        source=BinderWorldSource(config.rules),
        archetypes=archetypes,
        seeds=seeds,
        split=split_name,
        policies=policies,
        belief_factory=make_belief,
        environment_id="BinderBioPOMDP",
        code_version=code_version,
        scenario_version="core/9b891b2+071926d",
        max_steps=config.max_steps,
        record_store=record_store,
        evaluation_store=evaluation_store,
    )


def comparisons(run: BenchmarkRun) -> list[PairedComparison]:
    names = sorted(run.summary.policies)
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            out.append(paired_comparison(run.evaluations, a, b))
    return out


def regrets(run: BenchmarkRun, reference: str = "lookahead") -> list[RegretEstimate] | dict[str, str]:
    if reference not in run.summary.policies:
        return {"status": "not_computed", "reason": UNAVAILABLE_POLICIES.get(reference, "reference policy not run")}
    return [
        approximate_regret(run.evaluations, reference, p, initial_budget=INITIAL_BUDGET)
        for p in sorted(run.summary.policies)
        if p != reference
    ]


def result_document(run: BenchmarkRun, config: BenchmarkConfig, *, replay_paths: list[str]) -> dict[str, Any]:
    """The frontend-facing, truth-free JSON. Every number comes from evaluated episodes."""
    reg = regrets(run)
    return {
        "schema": RESULT_SCHEMA,
        "status": "real_run",
        "manifest": json.loads(run.manifest.model_dump_json()),
        "evaluator_config_version": run.manifest.evaluator_version,
        "label_rules": config.rules.as_dict(),
        "belief": {"n_particles": config.n_particles, "prior": PRIOR_PARAMS, "resampling": "systematic+rejuvenation"},
        "policy_availability": {
            **{name: "run" for name in run.summary.policies},
            **{k: v for k, v in UNAVAILABLE_POLICIES.items() if k not in run.summary.policies},
        },
        "summary": json.loads(run.summary.model_dump_json()),
        "paired_comparisons": [json.loads(c.model_dump_json()) for c in comparisons(run)],
        "approximate_regret": reg if isinstance(reg, dict) else [json.loads(r.model_dump_json()) for r in reg],
        "incident_counts": _incident_counts(run),
        "replays": replay_paths,
        "notes": [
            "Held-out seeds only; every policy played the identical (archetype, seed) worlds.",
            "Truth labels use campaign-eval/1 benchmark-engineering thresholds, not biological facts.",
            "Regret is approximate and model-based; it is only computed against a reference planner when one is run.",
        ],
    }


def _incident_counts(run: BenchmarkRun) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for i in run.manifest.incidents:
        counts.setdefault(i.policy_name, {}).setdefault(i.kind, 0)
        counts[i.policy_name][i.kind] += 1
    return counts


def export_showcase_replays(
    run: BenchmarkRun, out_dir: Path, archetype: str = "aggregation_kinetic_defect"
) -> tuple[list[str], int]:
    """Deterministic rule: the lowest seed of the run for the archetype; every policy's trace
    on that identical world. Writes frontend-ready replay JSON and the raw public JSONL."""
    seeds = sorted({r.seed for r, e in zip(run.records, run.evaluations) if e.archetype == archetype})
    if not seeds:
        return [], -1
    seed = seeds[0]
    out_dir.mkdir(parents=True, exist_ok=True)
    paths, bundle = [], {}
    store = PublicRecordStore(out_dir)
    for record, ev in zip(run.records, run.evaluations):
        if ev.archetype != archetype or record.seed != seed:
            continue
        store.save(record)
        bundle[ev.policy_name] = json.loads(replay_dto(record, complete=record.is_terminal).model_dump_json())
        paths.append(str(out_dir / f"{record.episode_id}.jsonl"))
    bundle_path = out_dir / f"showcase_{archetype}_seed{seed}.json"
    bundle_path.write_text(
        json.dumps({"archetype": archetype, "seed": seed, "selection_rule": "lowest held-out seed", "replays": bundle}, indent=2, sort_keys=True) + "\n"
    )
    return [str(bundle_path), *paths], seed


def np_seed_range(start: int, count: int) -> tuple[int, ...]:
    return tuple(int(x) for x in np.arange(start, start + count))
