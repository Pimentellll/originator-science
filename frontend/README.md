# MIRAGE Scientific Cockpit (frontend)

Causal rescue planning for failed de novo extracellular receptor-binding miniproteins. This app renders the
**public** record of a MIRAGE campaign: candidate lineage, evidence graph, causal belief by where the failure
is localised, a justification read-out, resources, the policy's recommended action, a scrubbable timeline,
same-seed policy comparison, and the benchmark lab. It never receives simulator truth.

> EGFR-inspired receptor-binding campaign. Semi-mechanistic synthetic benchmark: not a digital twin of any
> biology, not a validated simulator, and not a therapeutic discovery tool.

```bash
npm install
npm run dev            # LIVE is the default transport (needs the API; see below)
npm run dev:mock       # DEV / MOCK data, no backend
npm run typecheck && npm run lint && npm test && npm run build
```

## Live backend (E1)

`LiveApiTransport` talks to the real public API through the dev proxy (`/api/*` -> `MIRAGE_API_PROXY`, default
`http://localhost:8000`, prefix stripped). Endpoints used:

| Purpose | Endpoint |
| --- | --- |
| liveness | `GET /health` |
| reset a campaign | `POST /episodes {seed, policy_name}` then `GET /episodes/{id}/replay` (campaign profile, code version) |
| policy recommendation | `GET /episodes/{id}/recommendation` |
| execute an experiment or redesign | `POST /episodes/{id}/actions {action_type, candidate_id}` then `GET /episodes/{id}/replay` |
| scrub / stored replay | the replay record (also `openStored(episodeId)`) |
| same-seed comparison | one `reset -> recommend -> act -> replay` loop per configured policy, on the same seed |
| aggregate results (opt-in) | `GET /benchmarks`, `GET /benchmarks/{id}` (token-gated; `VITE_MIRAGE_BENCHMARKS=1`) |
| per-episode verdict (opt-in, **provisional**) | `GET /benchmarks/episodes/{id}` (token-gated; `VITE_MIRAGE_EVALUATION=1`) |

Availability is **configured, never probed**: `VITE_MIRAGE_POLICIES` lists the policies the server registers
(default `rescue_planner,greedy_eig,fixed_pipeline,random`), `VITE_MIRAGE_SEEDS` the seeds (default `9`). Every
other policy (Lookahead, PPO) is shown as **NOT RUN** without a request. The eval token is attached by the dev
proxy from `MIRAGE_EVAL_TOKEN`; it is never a `VITE_` variable and never reaches the bundle.

### What the backend does not give us yet

- **Server entry point.** `scripts/serve_api.py` serves the public API. `make_receptor_binder_service` registers `random`, `fixed_pipeline` and `rescue_planner`; `greedy_eig` is **not** served (the API answers 422 `unknown policy`, which the cockpit reports as NOT RUN, so set `VITE_MIRAGE_POLICIES` to the served list). `dev/h0_harness.py` assembles an app that additionally registers `greedy_eig` and a provisional verdict route for smoke testing.
- **No per-episode verdict route.** The public leak guard forbids the keys `correct` / `justified` on every
  route except `/benchmarks*`, so a verdict can only be served there. The harness provides
  `/benchmarks/episodes/{id}` to exercise the UI; H0 itself has none. Without it the terminal panel says
  "no evaluator verdict attached".
- **Recommendation is the action only.** No score, confidence, EIG or cost estimate, so the Next Action panel
  says so instead of showing placeholders.
- **No FailureLocalisation or JustificationCertificate from the backend.** Both exist in `mirage.belief` but the controller and API do not produce them. The three groups show `group p —` and the threshold
  row shows `NOT AVAILABLE`. Both are consumed automatically if the backend adds `failure_localisation` on the
  belief or a certificate on the state / replay.

## Growth benchmark

The growth routes are `#/results`, `#/episode/{run_id}/{episode_id}`, `#/lab`, `#/method`, `#/cockpit`,
`#/compare`, and `#/benchmark`. Route IDs are encoded as path segments and decoded by the route state.

The growth client uses the live API by default, with `VITE_MIRAGE_API_BASE` or `/api` as its base. Select the
offline client with `?growth=static` or `VITE_MIRAGE_GROWTH=static`; its data base defaults to `/growth-data`
and can be changed with `VITE_MIRAGE_GROWTH_DATA`. `npm run build:static` exports the experiment results into
`public/growth-data` and builds with static mode enabled. Set `PYTHON` to the repository venv interpreter when
needed, for example `PYTHON=../.venv/bin/python npm run build:static`. Generated growth data is ignored by git.

Live aggregate runs, episodes, and grids plus sandbox verdict/autoplay routes are token-gated. The dev proxy
adds `MIRAGE_EVAL_TOKEN` server-side; do not put the evaluator token in a `VITE_` variable. Public sandbox
create, measurement, and diagnosis endpoints do not require the token.

## Tests

`npm test` runs unit tests, including the live transport against a fake server that replays **real captured H0
output** (`src/lib/fixtures`). The real-backend suite has no fake fetch and is skipped unless a server is up:

```bash
MIRAGE_API_URL=http://localhost:8100 MIRAGE_EVAL_TOKEN=<same-local-value> npm test
```

`dev/smoke.mjs` is the browser smoke over the real stack (38 checks covering the ten demo requirements).

## Architecture

All backend access sits behind `ScientificTransport` (`src/lib/transport.ts`). Components never fetch and never
see wire DTOs.

`API DTOs (api.ts) -> fromApi.ts -> normalised public EpisodeRecord (wire.ts) -> validate.ts (public-only, contiguous, accounting) -> project.ts -> CockpitState frames -> components`

| Transport | Selected by | Notes |
| --- | --- | --- |
| `LiveApiTransport` | default, `?transport=live` | the real API |
| `MockTransport` | `?transport=mock`, `npm run dev:mock` | `ReplayTransport` over in-memory **DEV / MOCK** records |
| `ReplayTransport` | `?transport=replay` | fetches `{VITE_MIRAGE_REPLAY_BASE}/index.json` and the files it lists |

Derived in the frontend, not supplied: support / contradiction / unresolved edges come from `belief_before ->
belief_after` and observation `quality`; the counterfactual comes from the identical-seed comparison; the
justification rows come from the belief and the measurement log. The evidence-threshold verdict is **never**
inferred; it comes from a certificate or is NOT AVAILABLE.

## Trust boundary

- `validate.ts: assertPublic` rejects payloads containing keys like `_*`, `*truth*`, `*privileged*`, `*particle*`, `*latent*`, `*simulator*`, `*hidden*`, `world_class`.
- `environment_id` is surfaced only if it is a known profile name (`RECEPTOR_BINDER_RESCUE`); otherwise it is dropped, because an integrator could encode the scenario in it.
- There is no field for assay validity, model validity, true KD / koff, particles or the scenario world class. Scenario titles are neutral.

## Mock data (DEV / MOCK)

`src/lib/mock/` is authored in the normalised-record shape, so it exercises the same validation and projection as
live data. It is not a simulator run. Every mock view carries a **DEV / MOCK** pill. The authored long-horizon
trace is named `LONG-HORIZON · MOCK` and is never labelled PPO, Lookahead or the rescue planner. The mock
benchmark is watermarked and shows Rescue planner, Lookahead and PPO as NOT RUN.

## Layout

```
src/lib/        api.ts (DTOs) · fromApi.ts · wire.ts · types.ts · actions.ts · project.ts · derive.ts · validate.ts · adapters.ts · transports · mock/ · fixtures/
src/state/      session store (record -> frames, cursor, run / scrub / auto-run, campaign reset)
src/components/ candidate, justification, evidence graph (React Flow), belief (3 groups), action (+WHY?), resources, timeline
src/views/      Cockpit · ComparePolicies · BenchmarkLab
dev/            h0_harness.py (backend assembly for smoke) · smoke.mjs (browser smoke)
```

Designed for 16:9 desktop (>= 1440 px). There is no 3D viewer: the public contract carries lineage metadata only.
