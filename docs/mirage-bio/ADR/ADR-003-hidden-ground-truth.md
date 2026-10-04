# ADR-003: Simulator configuration is authoritative ground truth

> **LEGACY: MIRAGE-Bio v0.1 (growth / OD600 benchmark).** This document is the historical record of the first, separate environment. Status lines, "not started" notes and plans below date from 3-4 October 2026 and were **not** updated; the growth benchmark has since been implemented and run (see [mirage-bio/README.md](../README.md)). It does not describe the Binder rescue system. Current status: [START_HERE](../../START_HERE.md).

## Status

Accepted (3 October 2026).

## Context

Scoring needs an unambiguous truth for (a) the condition and (b) whether each
measurement was a diagnostic control. Any judgement-based truth, such as human
rating or LLM rating, would add variance and possible bias.

## Decision

- The hidden `EpisodeConfig` (condition, $K$, $S$, $r$, $X_0$, $\nu$, $n$, noise
  parameters) sampled from the frozen `scenario_v1.json` **is** the ground truth.
- The condition label is the truth for M1.
- Diagnostic-control status for M2 is computed from the visible action and the
  Gate-0-frozen diagnostic set. Gate 0 derives that set from the simulator.
  Reconstruction adequacy (Q1) is computed from noise-free hidden quantities
  ([DESIGN §15](../DESIGN.md#15-evaluation)).
- The configuration is hashed (SHA-256 of canonical JSON). Every record stores the
  hash. The runner refuses to run if it differs from the Gate 0 hash.
- The configuration never crosses the trust boundary
  ([DESIGN §12](../DESIGN.md#12-trust-boundary)). It is revealed only in the
  episode record after the episode ends.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Human adjudication of episodes | Slow, subjective, not reproducible. |
| LLM-judged correctness | Rejected by [ADR-005](ADR-005-no-llm-judge.md). |
| Truth derived from noisy observations | Circular; noise-dependent. |

## Consequences

- Positive: exact, reproducible scoring; any record can be re-scored.
- Negative: "truth" is only as meaningful as the model. Validity thresholds (5 %
  compression, lower bound $10\,\sigma_{\text{abs}} = 0.03$, fixed late window 12–18 h)
  are benchmark design decisions, not instrument facts
  (A-019, A-021; RISKS R-018).
