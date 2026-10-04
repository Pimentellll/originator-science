# Binder Rescue V2: preregistration (resource-constrained rescue)

**Status: LOCKED before any V2 policy is evaluated.** The lock is `experiments/preregistration/binder_rescue_v2/PREREGISTRATION.json`
(SHA-256 of this file, the spec, the seed manifest and the scoring code). Any change to those bytes is a *new version*
(V2.1, ...) reported separately; it never edits V2. Baseline V1 (`results/baseline_v1/`) is not touched.

## 1. Question

> When exhaustive characterisation is unaffordable, does adaptive long-horizon planning improve scientifically
> **justified** outcomes?

V1 showed that with the default budget (12.0 budget, 8.0 sample) the non-adaptive FixedPipeline already runs every assay
(8.25 / 3.15) and is hard to beat: it was at least as good as GreedyEIG in every regime. V1 therefore could not test the
question above. V2 changes only the **initial public resources**.

## 2. Design

* Hidden worlds are the same seeded worlds as V1's generator (same `sample_world`, same noise streams). Only the starting
  `ResourceState` differs, drawn from an RNG independent of the world and observation RNGs (a test proves the hidden
  world digests and the observation stream are unchanged).
* Every (archetype, seed) world is played at **all three strata** (fully crossed), so strata are compared on identical
  worlds. Archetypes: instability, aggregation_kinetic_defect, broken_assay, invalid_biological_model, misleading_proxy_trap.
* Policies see their resources only through the public state (as in V1). The stratum label is never given to a policy.

### Strata (frozen before any policy ran)

| stratum | budget | sample | initial SPR health | meaning |
|---|---|---|---|---|
| LOW | U[2.5, 4.5] | U[1.0, 2.0] | U[0.60, 1.0] | under-supplied lab; the 7-assay funnel is infeasible in every draw |
| MEDIUM | U[6.0, 10.0] | U[2.5, 5.0] | U[0.80, 1.0] | constrained; funnel affordable only in some draws, little room to redesign |
| HIGH | U[10.0, 14.0] | U[5.0, 9.0] | 1.0 | well supplied (brackets V1's 12 / 8); funnel always affordable |

Independent uniform draws, rounded to 2 decimals, seeded by `default_rng([0x52455343, seed, stratum_index])`.
The fixed funnel (stability, SEC, SPR, epitope, developability, assay control, orthogonal) costs **8.25 budget / 3.15 sample**.

Properties of the sampler (verified by tests; no policy involved):

* funnel affordable in **0%** of LOW draws (budget max 4.5 < 8.25 and sample max 2.0 < 3.15), about **32%** of MEDIUM
  draws, **100%** of HIGH draws;
* a justified `SELECT` is structurally possible (evaluator evidence rules need the five core assays plus the assay
  control, 6.75 budget / 2.9 sample, or 8.25 / 3.15 when the assay is broken) in **0%** of LOW draws,
  about 68% / 33% of MEDIUM draws, 100% of HIGH;
* a justified `REJECT`, `MODEL_INVALID` structural minimum or `ABSTAIN` needs only about 1.75 budget / 0.5 sample, so
  LOW is hard but not degenerate. (Belief thresholds add cost beyond these structural minima.)

**Consequence stated in advance:** in LOW, no policy can obtain a justified SELECT, so the `broken_assay` archetype
(truth-correct disposition SELECT) has a justified-rate ceiling of 0, and the LOW ceiling is at most 80% of worlds.
This reflects the frozen evaluator rulings and is not a defect of any policy.

### What is deliberately not randomised: simulated time

The brief asked for time to be randomised. In core, simulated time only accumulates; there is no deadline and no public
`time_remaining`, so time is neither binding nor observable. A hidden cap would be unfair to planners, and a start-time
offset would have no effect. Time is therefore **not constrained in V2** (recorded in `spec.json:unconstrained`). If core
adds a public deadline, a time stratum belongs in V2.1.

### Interim wrapper

Core has no initial-resource option. `ResourceConstrainedBinder` (in `rescue_v2.py`) runs core's unchanged `reset` and
then replaces the initial `ResourceState`. It must be retired once core exposes an official constructor argument.

## 3. Seeds

`seed_manifest.json`: development 1100-1149 (tuning allowed, never reported); held-out 60000-60049 (all 50 used, no
extension, replacement or dropping); learned-policy training seeds 100000-199999 with resources drawn from this same
spec. All sets are disjoint from each other and from V1's development (1000-1049) and held-out (50000-50099) seeds.
Planned size: 5 archetypes x 3 strata x 50 seeds = 750 episodes per policy (250 per stratum).

## 4. Policies and tuning rules

* Baselines, unchanged configuration from V1: Random, FixedPipeline, GreedyEIG (512 particles, 64 EIG samples).
* Lookahead and PPO: each must be **registered** (commit SHA and configuration hash) in a `policy_registry.json`
  committed before held-out evaluation. Tuning is allowed on development seeds only, and the number of tuning runs is
  disclosed. Nothing is retuned after held-out results exist.
* PPO: at least 3 independent training seeds (0, 1, 2), trained only on the reserved training range, final checkpoint at a
  fixed step budget chosen before evaluation. All seeds are reported; no best-seed selection. The PPO result in any
  contrast is the mean over its training seeds.
* No stratum parameter was chosen by running Lookahead or PPO; none has been run on V2.

## 5. Endpoints and analysis plan (frozen)

**Primary endpoint:** scientifically justified terminal rate (`justified` of campaign-eval/1), per stratum, per policy.

**Primary hypothesis H1 (LOW):** an adaptive planner achieves a higher justified rate than FixedPipeline.
Two primary contrasts, paired on the 250 LOW worlds: Lookahead - FixedPipeline, and PPO(mean over training seeds) -
FixedPipeline. Method: mean paired difference with a seeded percentile bootstrap (2000 resamples). Family-wise alpha 0.05
over the two contrasts (Bonferroni): **97.5% two-sided intervals**. H1 is supported for a planner only if the lower
bound of its interval is above 0. Otherwise the result is reported as not supported.

**Control H2 (HIGH):** FixedPipeline is expected to be strong where resources are plentiful. Contrasts are reported
descriptively; no superiority claim is drawn from HIGH.

**Secondary (descriptive, no hypothesis tests):** MEDIUM contrasts; correct rate; correct-but-unjustified rate;
justified abstention; budget, sample and experiments used; justified rate per budget spent; per-archetype results within
each stratum; GreedyEIG vs FixedPipeline per stratum; terminal Brier; localisation and mechanism F1; premature
aggregated SPR; reward-hacking flags.

**Approximate regret** against Lookahead (if run) is `utility = justified - 0.2 * budget_spent / initial_budget_of_that_world`
per world, labelled approximate and model-based.

**Pre-declared sensitivity analysis:** the belief engine's 512-particle posteriors proved unstable in V1 spot checks. After
the V2 results are in, the same worlds are rerun with 2048 particles for the policies that use the belief engine and
reported alongside, never instead of, the primary result.

**Reporting commitments:** every result is published including nulls and negative results; per-seed PPO results are
published; episodes are never excluded after the fact; incidents are listed.

## 6. Disclosures

* The designer had seen Baseline V1 results (FixedPipeline strong at 12 / 8) before writing the strata; that is what
  motivated them. No V2 parameter was derived from any policy output, and V1's held-out seeds are not reused.
* Resolution: V1's pooled paired justified-rate interval for n = 250 had half-width about 0.05, so V2 differences
  smaller than roughly 0.06-0.08 per stratum should not be expected to be resolved.
* Thresholds, label rules and the belief prior are the V1 benchmark-engineering parameters (`campaign-eval/1`), not
  biological facts. The belief prior is the benchmark's own assumption.
* LOW ceilings above mean a policy cannot "win" by selecting a good molecule; V2 can only show whether it localises and
  rejects, models-invalid, or abstains more justifiably under scarcity.

## 7. Artifacts

Raw per-episode public traces and privileged evaluations, aggregates, per-stratum and per-archetype JSON, paired
differences with bootstrap intervals and a provenance manifest, written under `results/binder_rescue_v2/` by a runner that
first calls `verify_lock` and refuses to run if any locked byte changed.
