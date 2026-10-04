# Frontend and API contract

Checked against `d182a2c` (`src/mirage/api`, `frontend/`).

The API exposes only public episode data: candidate lineage, structured action/observation events, resources,
`BeliefSummary`, policy recommendations, the terminal decision, public provenance and, behind a token, aggregate
evaluation outputs. It never exposes simulator truth, evaluator annotations, raw particles, true binding parameters,
assay validity or model validity. DTOs are built field by field (`mirage.api.dto`); a middleware blocks any
non-benchmark JSON body that carries a privileged-looking key even if a DTO bug let one through.

## Endpoints (`mirage.api/1`)

| Method and path | Purpose |
|---|---|
| `GET /health` | liveness and API version |
| `POST /episodes` `{seed?, policy_name?}` | reset an episode; returns the public state (201). Unknown policy → 422 `unknown policy` |
| `GET /episodes/{id}` | public state |
| `GET /episodes/{id}/actions` | currently available public actions |
| `POST /episodes/{id}/actions` `{action_type, candidate_id?, rationale?}` | take a public action; returns the step (event + state) |
| `GET /episodes/{id}/recommendation` | the policy's next action only: no score, EIG or confidence |
| `GET /episodes/{id}/replay` | the stored public trace (model-free replay) |
| `GET /benchmarks`, `GET /benchmarks/{id}` | aggregate results; require `X-Mirage-Eval-Token`; 404 if no store/token is configured; **not** configured by `scripts/serve_api.py` |

`make_receptor_binder_service` registers three policies: `random` (no terminal actions), `fixed_pipeline` and
`rescue_planner`. GreedyEIG, Lookahead and PPO are not served. The backend scenario is chosen at server start
(`--scenario`, default `COMPOUND_FAILURE`) and is never returned.

There is no per-episode verdict route: `correct` / `justified` keys are forbidden on every route except `/benchmarks*`.

## The Scientific Cockpit

Areas: Candidate, Evidence Graph, Causal Belief (grouped by failure locus), Justification, Resource State,
Recommended Next Action (+ "why"), Timeline/Replay, Policy Comparison (identical seeded worlds) and Benchmark Lab.
All backend access sits behind `ScientificTransport`; the live transport talks to the API above, mock and replay
transports serve watermarked DEV / MOCK or stored records. Availability is **configured, never probed**
(`VITE_MIRAGE_POLICIES`), and anything not served shows **NOT RUN**.

What the cockpit cannot show yet because the backend does not produce it: `FailureLocalisation`, a
`JustificationCertificate` verdict (it is never inferred, it shows NOT AVAILABLE), recommendation scores, a per-episode
evaluator verdict. See [frontend/README.md](../../frontend/README.md).

Any EGFR-inspired wording is illustrative only. Server-side DTO conversion is mandatory at the trust boundary.
