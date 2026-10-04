# Benchmark protocol

1. **Worlds.** Five canonical archetypes × seeded worlds. Every policy plays the identical `(archetype, seed)` worlds; the
   harness asserts identity with a per-world hidden-state digest (`world_digests.json`) and refuses mismatches.
2. **Seed discipline.** Development seeds (tuning allowed, never reported) and held-out seeds (reported once) are
   disjoint. Baseline V1: development 1000-1049, held-out 50000-50099 (50 per archetype used). V2 (preregistered):
   development 1100-1149, held-out 60000-60049. PPO training uses separate ranges. A manifest records which seeds
   were actually used.
3. **Belief.** Every belief-using policy starts from the identical seeded belief for a world (`seed` only), at a recorded
   particle count (512 in V1).
4. **Recording.** For every episode: scenario version, code version, seeds, policy configuration, public action trace,
   resource use and terminal decision. Public traces are stored as replayable JSONL; privileged evaluations are stored
   separately and are evaluator-only.
5. **Evaluation.** The privileged evaluator reads truth separately from the policy trace and reports correctness and
   justification separately ([METRICS](METRICS.md)). No model call is needed to replay an episode.
6. **Aggregation.** Wilson intervals per policy; paired bootstrap differences on identical worlds; per archetype, per
   regime, per scenario class.
7. **Provenance.** A `MANIFEST.json` records the git SHA, policy implementations and configs, evaluator config, belief
   config, timestamps, incident counts and SHA-256 of every exported file.
8. **Appending.** New policies run on the same held-out worlds with the manifest's world digests as an acceptance check and
   write to a **new** output directory; they never modify a published run.
9. **Frozen records.** Baseline V1 and the V2 preregistration are immutable. A change is a new version.

Commands: see [Reproduce the evaluation](../../README.md#reproduce-the-evaluation). Note that the current default belief
engine (adaptive tempering) differs from the one Baseline V1 ran on, so a fresh run is a *different* run, not a
reproduction.
