# Provenance and replay

Checked against `d182a2c` (`src/mirage/provenance`).

A public `ScientificEvent` contains `episode_id`, `step`, `candidate_id`, `action`, `observation` (none for redesign and
terminal actions), `child_candidate_id` (required for, and only for, `REDESIGN_*` actions, so lineage is recoverable
from the public trace), `belief_before`, `belief_after` (public belief snapshots with the `BeliefSummary` fields),
`resources_before`, `resources_after`, `policy_name` and an optional public `rationale`. It contains no hidden truth,
no evaluator annotation and no particle state.

An `EpisodeRecord` (`schema_version = mirage.provenance/1`) holds the contract and code version, environment id, seed,
the public initial state, the ordered events, the terminal decision and policy metadata. `digest()` is the SHA-256 of a
canonical JSON form. Records are stored as JSONL by `PublicRecordStore`.

**Replay** consumes the stored public trace. It calls no model, no PPO checkpoint, no environment and no RNG, so a saved
episode replays identically without any of them. Same seed and same implementation version reproduce the *event trace*;
replay itself never re-simulates.

`validate_record` checks contiguous steps, action/observation schema validity, resource accounting (including that a
measurement actually consumes resources), deterministic belief-payload shape and the absence of privileged fields. The
privileged evaluator reads truth separately from the policy trace and re-validates the record before scoring.

The Baseline V1 raw traces under `results/binder_campaign/public/` are public-only records of this form.
