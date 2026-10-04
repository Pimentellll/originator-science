# Trust boundary

## Public surface

Policies, LLM scientists, PPO, Greedy EIG, public APIs, frontend clients, and policy-visible replay may receive only ScientificAction, ScientificObservation, ResourceState, Candidate, AgentState, and public provenance. A Candidate carries lineage metadata only; it never carries true affinity, kinetics, aggregation, assay validity, or model validity.

## Privileged surface

The environment stores factorised truth under unmistakably private names such as _simulator_truth or _privileged_state. Evaluators may inspect it only through a separate evaluator-specific interface. There is no ordinary public hidden_truth() method.

## Enforcement

Public models must forbid extra fields and serialise deterministically. Tests must assert public JSON and replay contain no private fields or latent values. APIs must use public DTOs, and frontend payloads must be derived from those DTOs rather than environment internals.

~~~mermaid
flowchart LR
  Truth[_simulator_truth] --> Assay[private assay simulation]
  Assay --> Public[public observation]
  Public --> Policy
  Public --> Replay
  Truth -. privileged only .-> Evaluator
~~~
