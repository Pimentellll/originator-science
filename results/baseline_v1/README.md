# BASELINE V1

**Policies:** Random, FixedPipeline, GreedyEIG. Nothing else is in any numeric table.
**Worlds:** 5 canonical Binder scenarios x 50 held-out seeds = 250 worlds; every policy played every
world, giving 750 episodes. Do not rerun or overwrite this run. Later policies (Lookahead, PPO) are
*appended* on the same worlds and never change the files here.

| file | content |
|---|---|
| `MANIFEST.json` | git SHA, policy implementations/configs, evaluator version + config + label rules, environment/scenario version, belief config, timestamps, episode count, incident count, SHA-256 of every exported file |
| `seed_manifest.json` | exact development / held-out seeds, which held-out seeds were used, reserved training range |
| `world_digests.json` | hash of each seeded world's hidden root state: the identity an appended policy must reproduce |
| `aggregate.json`, `by_regime.json`, `by_archetype.json`, `by_scenario_class.json` | aggregate metrics with 95% Wilson intervals |
| `paired_differences.json` | A - B on identical worlds with 2000-resample seeded bootstrap 95% intervals, overall and per regime |
| `evaluations.jsonl` | one privileged evaluation per episode (EVALUATOR-ONLY; contains truth-derived fields) |
| `RESULTS.md` | headline tables generated from the numbers above |
| `../binder_campaign/public/*.jsonl` | raw public trace of every episode (replayable with no model, policy or RNG) |
| `../binder_campaign/privileged/` | the run's own per-episode evaluations and summary (EVALUATOR-ONLY) |
| `../binder_campaign/showcase/` | `aggregation_kinetic_defect` replays of all three policies on the lowest held-out seed |
| `../binder_campaign_benchmark.json` | the run's own frontend-facing aggregate document |

The exporter (`scripts/export_baseline_v1.py`) is read-only: it rebuilds the aggregate from the
750 per-episode evaluations and refuses to write unless it equals the aggregate the run wrote.

## Read these before using the numbers

* Thresholds, label rules and the agent-side prior are versioned benchmark-engineering parameters
  (`campaign-eval/1`), not biological facts. Core publishes no canonical failure thresholds yet.
* Truth-correct disposition for a good molecule behind a broken assay is SELECT (frozen ruling), so the
  baselines, whose closing rule abstains when the assay looks broken, score 0% correct there; their
  *justified abstention* rate is the relevant figure for that archetype.
* The belief engine ran at 512 particles. Spot checks on this run show the same evidence can give
  different posteriors at 512 vs 2048 particles, so belief-dependent decisions (notably invalid-model
  misses) are partly inference noise. A separate particle-count sensitivity run is recommended; it
  must not replace this baseline.
* `../binder_campaign_benchmark.json` contains non-numeric availability notes written at run time
  about policies that had not landed; they are not results.
* The path-dependent regime did not separate policies here: FixedPipeline already runs every assay
  within budget, so premature aggregated SPR (counted in `premature_aggregated_spr` for both
  adaptive and fixed policies) did not cost it a correct decision.

## Appending policies

Run new policies with `run_binder_benchmark(include_baselines=False, extra_policies=...,
expected_fingerprints=<MANIFEST world fingerprints>, expected_world_digests=<world_digests.json>)`
on `seed_manifest.json:held_out_used`, writing to a new output directory.
