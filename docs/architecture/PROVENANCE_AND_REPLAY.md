# Provenance and replay

A public ScientificEvent contains episode_id, step, candidate_id, action, observation, belief_before, belief_after, resources_before, resources_after, policy_name, and optional public rationale. It contains no hidden truth, evaluator annotation, or private particle state.

An episode records seed, public initial state, ordered ScientificEvent values, terminal decision, policy metadata, and contract/schema version. The record must replay the public UI without calling Claude, PPO, the environment RNG, or any model. Same seed and implementation version reproduce the event trace; replay consumes the stored public trace rather than resimulating it.

A privileged evaluator record may be stored separately or linked with access control. Required checks are contiguous steps, action/observation schema validity, resource accounting, deterministic source execution, and absence of privileged fields.
