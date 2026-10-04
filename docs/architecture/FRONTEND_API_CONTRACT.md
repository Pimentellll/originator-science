# Frontend and API contract

The API exposes only public episode data: candidate lineage identifiers, structured action/observation events, resources, BeliefSummary, policy recommendations, terminal decision, public provenance, and authorised aggregate evaluation outputs. Observations use named numeric measurements, quality, and public notes. The API never exposes simulator truth, evaluator-only annotations, raw particles, true binding parameters, assay validity, or model validity.

The Scientific Cockpit has Candidate, Evidence Graph, Causal Belief, Resource State, Recommended Next Action, Timeline/Replay, Policy Comparison, and Benchmark Lab areas. A policy comparison must use identical seeded worlds. Any EGFR-inspired language is illustrative only.

Planned endpoints include reset episode, read public state, take public action, read stored replay, and read authorised aggregate benchmark results. Server-side DTO conversion is mandatory at the trust boundary.
