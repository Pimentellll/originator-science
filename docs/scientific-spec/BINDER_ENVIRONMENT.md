# Binder BioPOMDP

Checked against `src/mirage/environments/binder/` at `d182a2c`.

The Binder BioPOMDP models rescue and maturation of a **synthetic** de novo extracellular receptor-binding
miniprotein after poor downstream function. It is a seeded simulator; every number is a modelling assumption, not a
wet-lab fact, and nothing in it predicts any real molecule or EGFR.

The environment owns private causal truth, public resources, assay behaviour, candidate lineage and terminal state. It
implements `reset(seed)`, `available_actions()`, `step(action)`, `agent_state()`, `is_terminal()` and `score()`. `score()` is
a local training utility (±1 for a correct/incorrect terminal minus 0.02 per budget unit spent); it is never scientific
evaluation. Public state carries no truth.

World classes: `SINGLE_FAILURE`, `COMPOUND_FAILURE`, `ASSAY_FAILURE`, `MODEL_FAILURE`, `MIXED`. A scenario label is an
environment-construction control and is never in public state or observations.

## Scenario registry

| Showcase scenario | World mode | Benchmark regime (harness tag, reporting only) |
|---|---|---|
| `instability` | `SINGLE_FAILURE` | myopic |
| `aggregation_kinetic_defect` | `COMPOUND_FAILURE` | path_dependent |
| `broken_assay` | `ASSAY_FAILURE` | invalid |
| `invalid_biological_model` | `MODEL_FAILURE` | invalid |
| `misleading_proxy_trap` | `MIXED` | adversarial |

The regime is a reporting tag from the benchmark harness (`ARCHETYPE_TAGS`). `BinderBioPOMDP.evaluator_truth` carries its own
`regime` string, which reports `myopic` for the `MIXED` world; Baseline V1 uses the harness tags.

## Scenario semantics versions

`BinderScenarioVersion` selects the world generator. **`BASELINE_V1` is the default and is frozen**: it is the
generator Baseline V1 ran on. **`SEMANTICS_V2`** (A5, commit `34a7fae`, tag `mirage-a5-scenarios`) makes each named
scenario's primary failure mechanisms contractual.

| Scenario | Primary failure (`SEMANTICS_V2`) | Secondary consequences (evaluator metadata) | Forbidden as primary |
|---|---|---|---|
| `instability` | folding | reduced stability assay signal | aggregation, affinity, kinetic, epitope, developability |
| `aggregation_kinetic_defect` | aggregation + kinetic | degraded SPR information; SPR instrument health loss after premature SPR | folding, affinity, epitope, developability |
| `broken_assay` | assay invalid | functional readout is uninterpretable | all molecular failures, model invalid |
| `invalid_biological_model` | model invalid | molecular engagement does not establish expected function | all molecular failures, assay invalid |
| `misleading_proxy_trap` | epitope + developability | favourable affinity proxy is non-diagnostic | folding, aggregation, affinity, kinetic, assay invalid, model invalid |

**Primary failures versus secondary consequences.** A primary failure is a mechanism the scenario is about: the
privileged truth labels (thresholded hidden state) must contain exactly these and no other molecular, assay or model
failure. A secondary consequence is a downstream effect or observable signature of the primary failure (for example
degraded SPR readings when the sample aggregates); it is recorded as metadata on `FailureLabels`
(`primary_failure_mechanisms`, `secondary_consequences`) and is **not** counted as an additional failure. Secondary
consequences and primary mechanisms are returned only by the evaluator accessor `evaluator_truth`.

**Why V2 exists.** Under `BASELINE_V1`, with the `campaign-eval/1` label rules and 300 seeds per scenario,
`aggregation_kinetic_defect` worlds failed aggregation, affinity, kinetic **and** developability in 300/300, and
`misleading_proxy_trap` worlds failed aggregation as well as epitope and developability in 300/300; the scenario names
did not describe the worlds. Under `SEMANTICS_V2` the label set equals the primary mechanisms in 300/300 worlds for
every scenario. Reproduce with `BinderBioPOMDP.from_showcase(name, scenario_version=...)` and
`BinderPrivilegedOracle(env).failure_labels("binder-000")`. `tests/binder/test_scenario_semantics_v2.py` asserts the
same against `evaluator_truth` over 32 seeds per scenario.

## Public interface

Resources start at budget 12.0, sample 8.0, simulated time 0.0, SPR health 1.0. `available_actions()` lists terminal
actions always and an experiment only if budget and sample cover its cost. The environment is deterministic for a given
`(scenario, seed)`.

## Label rule inconsistency

Two sets of failure-label thresholds coexist, both provisional:

| Factor | `campaign-eval/1` `LabelRules` (benchmark, and the belief schema used in V1/V2) | `BinderBioPOMDP.evaluator_truth` (H0 controller `evaluate()`) |
|---|---|---|
| folding failure | stability < 0.5 | stability < 0.5 |
| aggregation failure | monomer_fraction < 0.6 | monomer_fraction < 0.8 |
| affinity / kinetic | log_kd > -7.0 / log_koff > -2.0 | same |
| developability failure | liability > 0.4 | liability > 0.5 |

Benchmark results use `LabelRules`. An episode evaluated through the controller's `evaluate()` uses the second column.
They agree on the five canonical worlds under `SEMANTICS_V2`, and differ on borderline worlds; unifying them is open
work.

## Known simulator limits

- **Degraded-SPR bias mismatch.** For a sample with monomer fraction < 0.45 the public predictive model predicts a
  degraded SPR reading biased by +0.35 (σ 0.18). The environment adds a further +0.35 when it degrades the reading, so
  the realised bias is about +0.70 (measured: mean excess of `log_kd` over truth 0.72, sd 0.20, over 200 compound-failure
  worlds). The belief therefore models degraded SPR slightly wrongly.
- **Health-driven degradation is not modelled by the belief.** The environment also degrades SPR when instrument health
  < 0.70; the public likelihood allows `quality = "degraded"` only for aggregated particles. A zero-likelihood update
  raises `DegenerateBeliefError`, which the trackers count and skip.
- `ORTHOGONAL_FUNCTION` depends on `functional_epitope` and `assay_valid`, not on `model_valid`; a model failure is
  therefore identified by exclusion plus a failing downstream expectation, which is what the evaluator's
  `MODEL_INVALID` evidence rules encode.
- Simulated time only accumulates; there is no deadline and no public time-remaining.
