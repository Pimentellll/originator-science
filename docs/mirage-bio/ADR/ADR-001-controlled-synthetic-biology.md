# ADR-001: Use controlled synthetic biology rather than real biological data

## Status

Accepted (3 October 2026).

## Context

MIRAGE-Bio must test whether an AI scientist resolves an ambiguity that passive
observation cannot. Scoring requires knowing the true cause of every apparent plateau,
and the agent must be able to request new measurements on demand. Real data cannot
provide this within a hackathon:

- Real growth curves have no exact ground truth for whether the culture or the
  instrument flattened.
- Real experiments cannot be re-queried by an agent in seconds.
- No wet lab is available.

## Decision

Use a controlled synthetic world:
- a closed-form growth abstraction (Richards, ν = 8);
- a closed-form OD-like assay;
- hidden parameters sampled from a frozen, hashed distribution (`scenario-v1`).

Every assumption is labelled FACT, MODEL ASSUMPTION, SIMPLIFICATION or DESIGN
DECISION ([ANALYSIS §10](../ANALYSIS.md#10-scientific-assumptions)). The world is an
evaluation instrument, not a digital twin.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Real public growth-curve datasets | No ground truth for the cause of plateaus; no on-demand interventions. |
| Wet-lab integration | Not available; slow; out of scope. |
| Mechanistic multi-variable model (substrate ODEs, scattering physics) | More parameters and integration code without improving the evaluation. Closed forms suffice. |
| Purely abstract task (no biology) | Loses the realistic measurement-confound framing that makes the question meaningful. |

## Consequences

- Positive: exact ground truth; deterministic scoring; on-demand experiments;
  cheap, fast and reproducible.
- Negative: results say nothing about real organisms or instruments. This must be
  stated in every communication ([ANALYSIS §18](../ANALYSIS.md#18-scientific-communication-constraints)).
  Realism criticism is expected (RISKS R-004).
