# ADR 0009: Versioned scenario semantics

**Status:** accepted (A5, commit `34a7fae`). Baseline V1 showed that named scenarios did not describe their worlds
(for example `aggregation_kinetic_defect` also failed affinity and developability in every sampled world). The scenario generator is now selected by `BinderScenarioVersion`: `BASELINE_V1` stays the default and byte-for-byte frozen so V1 remains reproducible; `SEMANTICS_V2` makes each scenario's *primary failure mechanisms* contractual and records *secondary consequences* as evaluator-only metadata. Semantics changes are always a new version, never an edit.
