# MIRAGE Scientific Cockpit (frontend)

Vite + React + TypeScript. Renders the **public** record of a MIRAGE episode:
candidate lineage, evidence graph, causal belief, resources, the policy's
recommended next action, a replayable timeline, identical-seed policy
comparison, and the benchmark lab. It never receives simulator truth.

```bash
npm install
npm run dev          # http://localhost:5173, MockTransport by default
npm run typecheck && npm run lint && npm test && npm run build
```

Status: **E0** (mock transport; no backend dependency). E1 swaps in
`LiveApiTransport`, which already exists but has not been run against a backend.

## Transports

All backend access lives behind `ScientificTransport` (`src/lib/transport.ts`).
Components never fetch and never see wire DTOs.

| Transport | Selected by | Notes |
| --- | --- | --- |
| `MockTransport` | default, `?transport=mock` | `ReplayTransport` over in-memory **DEV / MOCK** records (`src/lib/mock/`). |
| `ReplayTransport` | `?transport=replay` | Fetches `{VITE_MIRAGE_REPLAY_BASE}/index.json` and the episode / comparison / benchmark files it lists. |
| `LiveApiTransport` | `?transport=live` | Provisional endpoint map in the file header. Proxy `/api` to `MIRAGE_API_PROXY` in `vite dev`. |

Data flow: `transport → adapters (validate public-only, contiguous, accounting) → project.ts (EpisodeRecord → CockpitState frames) → components`.
Reconciling with the backend means editing `liveApiTransport.ts`, `adapters.ts` and, if field names move, `wire.ts`. Components do not change.

## Contract

`src/lib/wire.ts` mirrors the frozen D0 documents and `src/mirage/core/contracts.py`
(commit `9fe2f8e`): `ScientificAction`, structured `ScientificObservation`
(`measurements: dict[str, float]`, required `quality`, `notes`; **no scalar value,
no generic metadata**), `BeliefSummary` (independent `p_*` marginals that do not
sum to 1), `ResourceState`, `ScientificEvent` (before/after belief and resources),
and the replay `EpisodeRecord`.

Provisional, optional extensions (the UI degrades gracefully without them):
`ScientificEvent.decision` (score, confidence, EIG, estimated cost, risk,
ranked alternatives), `ScientificEvent.active_candidate_after` (carries the new
candidate on `REDESIGN_*`, mirroring `AgentState.active_candidate`),
`EpisodeRecord.pending.recommendation` (live episodes),
`EpisodeRecord.evaluation` (authorised evaluator verdict), and resource key spelling.

Derived in the frontend, not supplied: support / contradiction / unresolved
edges come from `belief_before → belief_after` and observation `quality`
(`project.ts: deriveLinks`); counterfactuals come from the identical-seed
policy comparison, i.e. from public traces only.

## Trust boundary

- `validate.ts: assertPublic` rejects any payload containing keys like `_*`, `*truth*`, `*privileged*`, `*particle*`, `*latent*`, `*simulator*`, `*hidden*`, `world_class`.
- There is no type or field for assay validity, model validity (as truth), true KD/koff, particles, or the scenario world class. Scenario titles are neutral.
- Tests assert the mocks contain none of these and that the live transport refuses a leaking payload.

## Mock data

`src/lib/mock/` is DEV / MOCK scaffolding authored in the **wire** shape, so it
exercises the same validation and projection as a real record. It is not a
simulator run. Every view shows a **DEV / MOCK** pill; the benchmark mock is
watermarked and includes deliberate `NOT RUN` / `n/a` cells. Replace by pointing
`ReplayTransport` at backend event files.

## Layout

```
src/lib/        wire.ts · types.ts · actions.ts · project.ts · derive.ts · validate.ts · adapters.ts · transports · mock/
src/state/      session store (record → frames, cursor, run/scrub/play) · hash route
src/components/ candidate, evidence graph (React Flow), belief, action (+WHY?), resources, timeline
src/views/      Cockpit · ComparePolicies · BenchmarkLab
```

Designed for 16:9 desktop (≥ 1440 px wide). The 3D molecule viewer is deliberately
not included: the public contract carries lineage metadata only.
