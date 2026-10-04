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
| `POST /episodes` `{seed?, policy_name?, scenario?, scenario_version?}` | reset an episode; returns the public state (201). Unknown policy → 422 `unknown policy`; unknown scenario / version → 422. `scenario` and `scenario_version` are orchestration metadata chosen by the human running the demo: never policy input, never echoed or recorded (only the semantics version is, as `environment_id` `PROFILE/VERSION`) |
| `GET /episodes/{id}` | public state |
| `GET /episodes/{id}/actions` | currently available public actions |
| `POST /episodes/{id}/actions` `{action_type, candidate_id?, rationale?}` | take a public action; returns the step (event + state) |
| `GET /episodes/{id}/recommendation` | the policy's next action only: no score, EIG or confidence |
| `GET /episodes/{id}/replay` | the stored public trace (model-free replay) |
| `GET /version` | MIRAGE version, git SHA (+ dirty flag), commit date, API and contract versions, default and available scenario semantics, Python version. No paths, no secrets |
| `GET /policies` | policy catalogue `{name, display_name, kind, available, description, reason}`; only genuinely wired policies are `available` (Lookahead and PPO are listed as not available, with the reason) |
| `GET /scenarios` | human-facing demo scenarios `{id, title, summary, cli_name, is_default}` (orchestration metadata) |
| `GET /diagnostics` | cached real self-checks (environment, deterministic smoke, record/replay, leak guard, policies). No simulator or evaluator state |
| `GET /benchmarks`, `GET /benchmarks/{id}` | aggregate results; require `X-Mirage-Eval-Token`; 404 if no store/token is configured; **not** configured by `scripts/serve_api.py` |
| `GET /benchmarks/episodes/{id}` | per-episode `correct` / `justified` verdict and its evidence checks; requires `X-Mirage-Eval-Token` (`serve_api.py` enables it when `MIRAGE_EVAL_TOKEN` is set), only after the episode is terminal (409 before), and only allow-listed fields are returned (no scenario class, archetype, regime or truth labels) |

`make_receptor_binder_service` registers four policies: `random` (no terminal actions), `fixed_pipeline`, `rescue_planner`
and `greedy_eig`. Lookahead and PPO are not served. The default backend scenario is chosen at server start (`--scenario`,
default `COMPOUND_FAILURE`; `--scenario-version`, default `SEMANTICS_V2`) and is never returned; a client may choose another per
episode with `scenario` / `scenario_version`.

`correct` / `justified` keys are forbidden on every route except `/benchmarks*`, which is why the verdict route lives there.

## The Scientific Cockpit

Areas: Candidate, Evidence Graph, Causal Belief (grouped by failure locus), Justification, Resource State,
Recommended Next Action (+ "why"), Timeline/Replay, Policy Comparison (identical seeded worlds) and Benchmark Lab.
All backend access sits behind `ScientificTransport`; the live transport talks to the API above, mock and replay
transports serve watermarked DEV / MOCK or stored records. Availability comes from `GET /policies`
(`VITE_MIRAGE_POLICIES` is only the fallback for older servers), and anything not served shows **NOT RUN** / **NOT AVAILABLE**.

What the cockpit cannot show yet because the backend does not produce it: `FailureLocalisation`, a
`JustificationCertificate` verdict (it is never inferred, it shows NOT AVAILABLE), recommendation scores. See [frontend/README.md](../../frontend/README.md).

Any EGFR-inspired wording is illustrative only. Server-side DTO conversion is mandatory at the trust boundary.
