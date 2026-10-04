# ADR-006: Demo is an offline replay of saved evidence

> **LEGACY: MIRAGE-Bio v0.1 (growth / OD600 benchmark).** This document is the historical record of the first, separate environment. Status lines, "not started" notes and plans below date from 3-4 October 2026 and were **not** updated; the growth benchmark has since been implemented and run (see [mirage-bio/README.md](../README.md)). It does not describe the Binder rescue system. Current status: [START_HERE](../../START_HERE.md).

## Status

Accepted (3 October 2026).

## Context

Live demos that call an LLM API can fail (network, rate limits, latency) and are not
reproducible: the model used, `claude-opus-5-5`, accepts no sampling controls. A
live run would also tempt selective presentation.

## Decision

- The demo replays saved `EpisodeResult` JSON records step by step
  (`python -m mirage.demo.replay`, [DESIGN §20](../DESIGN.md#20-demo-replay-design)).
- It needs no network and no API key.
- Demo episodes are Claude runs on the matched demo pair, each run **once** after
  the prompt freeze and shown as-is. Re-runs are allowed only for `API_FAILURE`.
- Demo episodes are not part of the evaluation matrix. Quantitative claims come
  only from the committed results table.
- Pre-rendered figures and a terminal capture are committed as backup.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Live API call during the pitch | Fragile; non-reproducible; selection risk. |
| Web UI or dashboard | Out of scope (stop rule 5). |
| Slides only, no replay | Weaker evidence that the system works end to end. |

## Consequences

- Positive: robust demo; every number on screen is traceable to a committed file.
- Negative: no "live" moment. Mitigated by replaying genuine, unedited transcripts
  with the ground-truth reveal.
