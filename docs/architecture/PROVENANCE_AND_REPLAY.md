# Provenance and replay

Each episode records a seed, public initial state, ordered actions, public observations, resource transitions, terminal decision, policy metadata, and contract/schema version. It must replay offline without a model call and regenerate the same public event sequence for the same implementation version and seed.

Private truth must not enter policy replay or frontend serialization. A privileged evaluator record may be stored separately or linked with access control; it is not a public replay payload. The evaluator independently distinguishes correct terminal labels from justified conclusions.

Required replay checks: contiguous event order, action/observation schema validity, resource accounting, deterministic seeded execution, and absence of privileged fields.
