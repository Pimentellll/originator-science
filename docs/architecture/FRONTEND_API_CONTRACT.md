# Frontend and API contract

The API exposes only public episode data: candidate lineage identifiers, action/observation events, resources, belief summaries, policy recommendations, terminal decision, public provenance, and aggregate evaluation outputs approved for display. It must never expose simulator truth, evaluator-only annotations, raw particles, true binding parameters, assay validity, or model validity.

The Scientific Cockpit has Candidate, Evidence Graph, Causal Belief, Resource State, Recommended Next Action, Timeline/Replay, Policy Comparison, and Benchmark Lab areas. A policy comparison must use identical seeded worlds. Any EGFR-inspired language is illustrative only.

Suggested endpoints are planned rather than implemented: create/reset episode, read public state, take public action, read replay, and read authorised aggregate benchmark results. Server-side DTO conversion is mandatory at the trust boundary.
