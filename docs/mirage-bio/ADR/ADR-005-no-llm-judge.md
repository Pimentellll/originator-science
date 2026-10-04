# ADR-005: No LLM judge in evaluation

> **LEGACY: MIRAGE-Bio v0.1 (growth / OD600 benchmark).** This document is the historical record of the first, separate environment. Status lines, "not started" notes and plans below date from 3-4 October 2026 and were **not** updated; the growth benchmark has since been implemented and run (see [mirage-bio/README.md](../README.md)). It does not describe the Binder rescue system. Current status: [START_HERE](../../START_HERE.md).

## Status

Accepted (3 October 2026).

## Context

LLM judges are often used to grade agent reasoning. Here they would introduce
non-determinism, cost, possible bias towards fluent rationales, and circularity
(an LLM grading an LLM's science). Everything we need to score is already defined
by hidden ground truth and the measurement log.

## Decision

- The evaluation path (`evaluation/metrics.py`, `evaluation/runner.py summarize`,
  `scripts/gate0.py`) contains no LLM call and does not import `anthropic`. This is
  enforced by T-012.
- M1–M4 and the optional O1/O2 are pure functions of the episode record and the
  hidden configuration ([DESIGN §15](../DESIGN.md#15-evaluation)).
- Free-text rationales and optional `declare_state` notes are recorded and shown in the demo.
  They are never scored.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| LLM grading of rationale quality | Non-deterministic; unverifiable; circular. |
| Keyword scoring of rationales | Brittle and gameable; adds no ground truth. |
| Human grading | Slow; subjective; not reproducible within the timeline. |

## Consequences

- Positive: scores are exact, cheap, and reproducible from committed records.
- Negative: reasoning quality beyond the measured actions and diagnosis is not
  quantified. Transcripts are available for qualitative inspection only, labelled
  as such.
