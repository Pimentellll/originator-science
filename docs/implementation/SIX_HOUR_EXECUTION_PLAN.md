# Six-hour execution plan

First freeze core contracts and leakage tests. In parallel, implement Binder environment, particle belief/baselines, evaluator/API/provenance, PPO adapter, and frontend against those contracts. Then integrate actions, run the gates, create deterministic seeded demonstrations, and report only executed results.

If a contract ambiguity blocks a package, report it to integration rather than creating a competing public type. Prioritise determinism, trust boundary, action semantics, and replay before polish.
