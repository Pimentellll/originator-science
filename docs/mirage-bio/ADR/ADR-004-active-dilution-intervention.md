# ADR-004: Dilution is the primary active diagnostic intervention

## Status

Accepted (3 October 2026).

## Context

The two hidden conditions produce passive readings that cannot reliably be told
apart. The agent needs one intervention that:

- is standard laboratory practice (A-004);
- separates the conditions when used correctly;
- can be used incorrectly (too early, too little, too much dilution, or not
  back-corrected).

## Decision

The active intervention is `measure_od(time_h, dilution_factor, replicates)`:
- a retained aliquot from any hour 0–18 is diluted exactly by $d \in [1, 100]$ and
  read;
- the culture is unaffected;
- each replicate costs 1 of 6 budget units.

The tool description is neutral: it never mentions saturation, linear range or the
intended use ([DESIGN §9](../DESIGN.md#9-agent-tool-api)). A measurement counts as a
**valid diagnostic control** only if it is late-stage (fixed visible window $t \in [12, 18]$ h), diluted
($d > 1$), in the useful region, and obtained before the diagnosis.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Path-length or instrument-setting changes | Less universal; needs extra instrument modelling. |
| Orthogonal assay (plate counts) | Second assay ([ADR-002](ADR-002-single-assay-mvp.md)). |
| Extending observation time | Does not resolve the ambiguity (both curves stay flat). |
| Spiking known standards (calibration curve) | Valid control but more complex; Phase 2 candidate. |

## Consequences

- Positive: a single, interpretable, standard control; strong separation
  (design-time: `GoodScientist` accuracy 1.00).
- Positive: the validity definition rejects trivial "low OD" readings (SVR-007).
- Negative: the control is well known, so a capable LLM may solve the task
  easily (RISKS R-007). This is acceptable: the environment measures action under
  ambiguity, and the result is reported honestly.
