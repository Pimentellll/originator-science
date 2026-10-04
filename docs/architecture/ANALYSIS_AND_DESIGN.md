# MIRAGE analysis and design rationale

Rationale for the design choices, checked against `d182a2c`. For what exists and its status see
[START_HERE](../START_HERE.md); for the contracts see the other documents in this directory.

## Problem

A failed de novo binder campaign has overlapping, co-occurring explanations across three loci (molecule, experiment,
biological model). A policy must observe noisy evidence, keep uncertainty over several mechanisms at once, choose
experiments under cost and path dependence, and make a bounded terminal claim. **Correctness alone is insufficient**:
independent evaluation checks whether the recorded evidence supports the claim (CORRECT ≠ JUSTIFIED).

## Alternatives rejected

| Rejected | Why |
|---|---|
| a single mutually exclusive failure label | cannot represent compound failure (aggregation + kinetic defect) |
| a deterministic pass/fail assay table | makes inference trivial; real assays are noisy and overlapping |
| a sequence-generating RL action space | MIRAGE evaluates campaign decisions, not amino-acid generation |
| using the training reward as the evaluator | conflates optimisation with scientific justification (ADR 0006) |
| a language-model judge | non-reproducible; the evaluator is deterministic over saved records |

## Selected design

- **Environment.** `BinderBioPOMDP` owns a private, factorised causal state and emits overlapping stochastic structured
  observations. Resources and SPR instrument health are a separate public component. Redesign creates a new lineage
  member through explicitly synthetic transitions.
- **Belief.** A seeded particle posterior over the factorised state (adaptive-tempering SMC with resample-move),
  summarised as eight non-exclusive failure marginals and a derived locus view.
- **Policies.** One public contract, six policies (Random, FixedPipeline, GreedyEIG, ReceptorRescuePlanner, Lookahead,
  PPO).
- **Evaluation.** A privileged evaluator that reads a public trace plus truth labels and scores *correct* and
  *justified* separately, with a reward-hacking suite.
- **Provenance.** Public events recorded per step; model-free replay.
- **Interface.** A DTO-bounded API and a cockpit that never receive truth.

## Planning design and the honest state of the evidence

GreedyEIG is deliberately myopic and was expected to be competitive on myopic worlds, with path-dependent worlds (an SPR
reading on an aggregated sample damages the instrument) exposing its limit. **Baseline V1 did not show that.** With the
default resources FixedPipeline already runs every assay, beat GreedyEIG on justified rate (74% vs 64%), and the
path-dependent regime did not separate policies ([BASELINE_V1](../evaluation/BASELINE_V1.md)). Long-horizon planners
(Lookahead; PPO) are a hypothesis to be tested on the preregistered resource-constrained V2 benchmark, which has not
been run. PPO is a pragmatic swappable planner, not a claim of definitive scientific planning.

## Design risks that materialised

| Risk | What happened |
|---|---|
| scenario labels not matching worlds | V1 worlds carried extra failures; fixed by `SEMANTICS_V2` (A5) |
| unstable posterior | SIR degeneracy at 512 particles; adaptive tempering added; convergence gate still unmet |
| preregistration drift | A5 touched a V2-locked file; lock fails verification pending a V2.1 decision |
| evaluator / simulator label mismatch | two threshold sets coexist (`campaign-eval/1` vs `evaluator_truth`) |
| belief / simulator model mismatch | degraded SPR bias +0.70 realised vs +0.35 assumed |
| leakage | key scanner, DTO boundary and sentinel tests in place; free text is not scanned |

## Claim boundaries

MIRAGE is a synthetic, semi-mechanistic benchmark. It is not a digital twin, a therapeutic discovery system, a
clinical or validated EGFR predictor, a wet-lab replacement or an exact physical simulator. Sequence- or
structure-level design engines are out of scope and none is implemented; the redesign interface is the only place such an
engine could plug in.
