# Binder Rescue V2: implementation and lock status

The preregistration itself is [BINDER_RESCUE_V2.md](BINDER_RESCUE_V2.md). It is **hash-locked** (the lock covers that
file, `spec.json`, `seed_manifest.json` and the scoring code) and is never edited in place; this separate document
records what exists at `d182a2c`.

## What V2 is

A **resource-constrained rescue** benchmark. It asks: when exhaustive characterisation is unaffordable, does adaptive
long-horizon planning improve scientifically *justified* outcomes? It changes only the initial public resources of the
same hidden worlds as V1, fully crossed over three strata.

| Stratum | Budget | Sample | Initial SPR health | Funnel (8.25 / 3.15) affordable | Justified `SELECT` structurally possible |
|---|---|---|---|---|---|
| LOW | U[2.5, 4.5] | U[1.0, 2.0] | U[0.60, 1.0] | 0% | 0% |
| MEDIUM | U[6.0, 10.0] | U[2.5, 5.0] | U[0.80, 1.0] | ≈32% | ≈68% (valid assay) / ≈33% (broken assay) |
| HIGH | U[10.0, 14.0] | U[5.0, 9.0] | 1.0 | 100% | 100% |

The strata were **frozen before any Lookahead or PPO behaviour was inspected**; none has been run on V2. The designer
had seen Baseline V1 (FixedPipeline strong at 12 / 8), which motivated the strata, and that is disclosed in the
preregistration.

## What exists

| Piece | State |
|---|---|
| Spec, strata, sampler (`rescue_v2.py`), `ResourceConstrainedBinder` wrapper, `RescueWorldSource` | implemented and tested (sampler properties, world identity) |
| Hash lock (`PREREGISTRATION.json`), `seed_manifest.json`, `scripts/freeze_rescue_v2.py` | present |
| **V2 runner** (`results/binder_rescue_v2/` writer that calls `verify_lock` first) | **does not exist** |
| `policy_registry.json` for Lookahead and PPO | **does not exist** |
| PPO training on the V2 seed range and resource spec (training seeds 100000-199999, three seeds) | **not done**; the existing RL stack uses its own ranges (`10,000,000+`) and the nominal 12 / 8 resources |
| Held-out V2 results (seeds 60000-60049) | **none**. No V2 held-out seed has been used |

## Lock integrity on this branch: FAILING

`tests/campaign/test_campaign_rescue_v2.py::test_committed_lock_matches_the_files_on_disk` and
`::test_lock_detects_any_change_to_spec_scoring_or_doc` fail with
`src/mirage/evaluation/campaign/truth.py changed since preregistration`.

Cause: A5 (`34a7fae`) added `primary_failure_mechanisms` and `secondary_consequences` (both defaulting to `()`) to
`FailureLabels` in `truth.py`, one of the locked scoring files, on the integration branch, whereas the V2 lock was made on
the evaluation branch before A5. The change adds metadata only; `correct_terminal_decisions`, evidence rules and
thresholds are untouched. The failure is **not masked**: the lock detecting a change is exactly its job.

Options (a decision for the project owner, not taken here):

1. **Issue V2.1.** Re-lock with the A5 `truth.py`, report V2.1 separately, state that V2 held-out was never evaluated. No
   policy has been run on V2, so nothing is contaminated.
2. Revert the A5 metadata fields from `truth.py` (moving them out of a locked file) and keep the V2 lock as is.

Related observation for V2.1: the V2 spec reuses the `BASELINE_V1` generator by design (the default). If V2.1 were to adopt
`SEMANTICS_V2` worlds it would no longer be "the same worlds as V1", and the claim in the preregistration would need to be
restated.

## Rules that still hold

No V2 parameter may be derived from any policy output; development seeds 1100-1149 are for tuning only; the number of
tuning runs must be disclosed; PPO results are reported for all training seeds; nulls and negatives are published.
