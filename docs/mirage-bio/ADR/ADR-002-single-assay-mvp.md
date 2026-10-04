# ADR-002: One OD600-like assay for the MVP

> **LEGACY: MIRAGE-Bio v0.1 (growth / OD600 benchmark).** This document is the historical record of the first, separate environment. Status lines, "not started" notes and plans below date from 3-4 October 2026 and were **not** updated; the growth benchmark has since been implemented and run (see [mirage-bio/README.md](../README.md)). It does not describe the Binder rescue system. Current status: [START_HERE](../../START_HERE.md).

## Status

Accepted (3 October 2026).

## Context

The scientific question concerns one confound: measurement nonlinearity masking
continued growth. Adding assays (fluorescence, plate counts, microscopy) would
create new confounds, new validity proofs and new agent options. That multiplies
the design and verification work beyond what can be done by Sunday 14:45 BST.

## Decision

The MVP has exactly one assay: an OD600-like reader with response
$f(x) = x[1+(x/S)^n]^{-1/n}$, $n = 8$, and Gaussian heteroscedastic noise
([DESIGN §5.3–5.6](../DESIGN.md#5-mathematical-design)). The only active
intervention is aliquot dilution with remeasurement
([ADR-004](ADR-004-active-dilution-intervention.md)). Additional assays are Phase 2
([DEVELOPMENT_PLAN §9](../DEVELOPMENT_PLAN.md#9-expansion-plan)).

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| OD plus orthogonal assay (e.g. simulated colony counts) | Introduces a choice between control types and a cost model; needs its own validity proof. |
| Generic multi-assay interface for future use | Unneeded abstraction (stop rule 12). |
| Fluorescence reporter assay | Different artefacts (inner filter, photobleaching); a second scenario. |

## Consequences

- Positive: one validity proof (Gate 0), small code surface, clear story.
- Negative: cannot test whether agents choose between different kinds of control.
  That is deferred deliberately.
