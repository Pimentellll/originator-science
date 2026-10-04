# Baseline V1: analysis

**Status: frozen, historical, immutable.** Data: [`results/baseline_v1/`](../../results/baseline_v1/RESULTS.md)
(`MANIFEST.json` carries SHA-256 digests; tag `mirage-baseline-v1` = `5c47262`). This document interprets the published
numbers. It changes none of them, and it never reruns the benchmark.

## What was run

Random, FixedPipeline and GreedyEIG on 5 archetypes × 50 held-out seeds = 250 worlds; every policy on every world;
750 episodes; 0 incidents. Code `1c2ed6e`, evaluator `campaign-eval/1`, scenario generator `BASELINE_V1`, belief =
512 particles with the pre-tempering SIR + resample-move engine, default resources (12.0 budget, 8.0 sample).

## Headline (95% Wilson intervals)

| Policy | Correct | Justified | Correct but unjustified | Justified abstention | Budget | Sample | Experiments |
|---|---|---|---|---|---|---|---|
| FixedPipeline | 76% [70-81] (189/250) | **74% [68-79]** (185/250) | 2% (4/250) | 20% | 8.25 | 3.15 | 7.00 |
| GreedyEIG | 71% [65-76] (178/250) | 64% [58-70] (160/250) | 7% (18/250) | 20% | 7.40 | 3.17 | 6.01 |
| Random | 27% [22-33] (68/250) | 2% [1-5] (6/250) | 25% (62/250) | 6% | 3.12 | 1.28 | 1.64 |

Paired on the identical 250 worlds (seeded bootstrap, 2000 resamples, 95%): FixedPipeline − GreedyEIG justified rate
**+0.100 [+0.048, +0.148]** (35 worlds justified only by FixedPipeline, 10 only by GreedyEIG, 150 by both); correct
+0.044 [+0.004, +0.084]; correct-but-unjustified −0.056 [−0.092, −0.020]; FixedPipeline used 0.85 [0.53, 1.16] more budget
and 0.99 [0.76, 1.22] more experiments.

## What the result says

1. **FixedPipeline beat GreedyEIG on justified rate.** The information-gain policy did not win, and the interval excludes
   zero.
2. **GreedyEIG used somewhat fewer resources** (about 10% less budget, one fewer experiment), and the saving did not translate
   into higher justification.
3. **Greedy was often correct by elimination without directly measuring the responsible failure.** Its 18 correct-but-
   unjustified episodes (7%) are concentrated in `instability` (13 of 50 worlds). In all 13 the trace never contains
   `MEASURE_STABILITY` (for example SPR, assay control, SPR, then `REJECT`): the decision was right, but the rejection was
   not evidenced by an assay of the failing factor, so `failure_evidenced` failed.
4. **Random shows the metric works.** 27% correct, 2% justified: almost all of its correct answers are lucky, and the
   evaluator says so.
5. **Baseline V1 exposed benchmark and scientific problems rather than proving a preferred policy wins:**
   - the default budget lets the fixed funnel run in full, so the benchmark could not test adaptive planning;
   - scenario labels did not describe the worlds ([A5 / `SEMANTICS_V2`](../scientific-spec/BINDER_ENVIRONMENT.md#scenario-semantics-versions));
   - the 512-particle posterior was unreliable (spot checks gave different posteriors at 512 vs 2048), so belief-
     dependent decisions, notably invalid-model misses, partly reflect inference noise ([B4A](../validation/B4A_CONVERGENCE_RESULTS.md));
   - the path-dependent regime did not separate policies: FixedPipeline already runs every assay within budget, so
     premature aggregated SPR cost it no correct decision.

## By archetype (justified rate)

| Archetype | FixedPipeline | GreedyEIG | Random | Note |
|---|---|---|---|---|
| `instability` | 98% | 70% | 2% | Greedy's elimination-style `REJECT`s |
| `aggregation_kinetic_defect` | 100% | 100% | 8% | Greedy used 7.04 budget vs 8.25 |
| `broken_assay` | 0% | 0% | 0% | truth-correct disposition is `SELECT`; both baselines abstain, 100% *justified abstention* |
| `invalid_biological_model` | 72% | 50% | 0% | the largest FixedPipeline margin; posterior-noise sensitive |
| `misleading_proxy_trap` | 100% | 100% | 2% | Greedy used more budget than the funnel (10.34 vs 8.25) |

In `broken_assay` the frozen ruling makes `SELECT` the truth-correct decision for a good molecule behind a broken assay
(with orthogonal support). The baselines' closing rule abstains when the assay looks broken, so they score 0% *correct*;
their justified-abstention rate (100%) is the relevant figure.

## Limits of this baseline

Single run of 50 seeds per archetype (intervals are wide for per-archetype cells); thresholds, label rules and the agent
prior are benchmark-engineering parameters, not biological facts; labels used `campaign-eval/1`
`LabelRules`; the run was a pre-tempering belief engine. Later policies are *appended* on the same worlds in new
directories; nothing here is overwritten.

## Reproducing

`scripts/export_baseline_v1.py` is read-only on the run: it rebuilds the aggregates from the 750 stored per-episode
evaluations and refuses to write unless they equal the run's own. A fresh `run_binder_benchmark.py` on the current tree
would use adaptive tempering and is therefore a different run; check out tag `mirage-baseline-v1` to rerun V1 itself.
