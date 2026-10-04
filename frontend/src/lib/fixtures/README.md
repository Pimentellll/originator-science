# Fixtures

`replay-*`, `state-*`, `recommendation-*`: **real public API output** captured from the H0 backend
(`feat/mirage-integration` @ 4747deb: `make_receptor_binder_service`, the frozen public API, the
real Binder environment and particle belief) for seed 9. `rescue_planner` and `greedy_eig` were
registered by the capture harness; H0's own service registers only `random` / `fixed_pipeline`.

`evaluation-*`: real H0 `CampaignEvaluator` verdicts, served by a **harness-only** route
(`/benchmarks/episodes/{id}`, token-gated; H0 has no per-episode evaluation endpoint). Truth-derived
diagnostics were removed; the frontend reads only correct / justified / lucky-correct /
supported-but-wrong / unnecessary redesigns / justification checks.

`benchmark-summary.schema-fixture.json`: schema-exact `BenchmarkSummary` dumped from the repo's own
pydantic models with **placeholder numbers**. It only tests the aggregate adapter and must never be
shown as a result.
