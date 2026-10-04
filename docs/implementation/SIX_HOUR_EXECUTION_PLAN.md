# Six-hour execution plan (historical)

> This was the hackathon-day plan written before implementation. It is retained as a record and does not describe
> current status; see [START_HERE](../START_HERE.md) for that.

First freeze core contracts and leakage tests. In parallel, implement the Binder environment, particle belief and
baselines, evaluator/API/provenance, the PPO adapter and the frontend against those contracts. Then integrate actions,
run the gates, create deterministic seeded demonstrations, and report only executed results.

If a contract ambiguity blocked a package, it was reported to integration rather than creating a competing public type.
Determinism, trust boundary, action semantics and replay took priority over polish.
