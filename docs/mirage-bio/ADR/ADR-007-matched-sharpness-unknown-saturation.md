# ADR-007: Construct passive ambiguity by matched transition sharpness and an unknown saturation scale

> **LEGACY: MIRAGE-Bio v0.1 (growth / OD600 benchmark).** This document is the historical record of the first, separate environment. Status lines, "not started" notes and plans below date from 3-4 October 2026 and were **not** updated; the growth benchmark has since been implemented and run (see [mirage-bio/README.md](../README.md)). It does not describe the Binder rescue system. Current status: [START_HERE](../../START_HERE.md).

## Status

Accepted (3 October 2026). Subject to confirmation by Gate 0.

## Context

The corrected causal design requires Condition A (`BIOLOGICAL_PLATEAU`) to plateau
inside the assay's trustworthy range (compression ≤ 5 %), and Condition B
(`MEASUREMENT_ARTIFACT`) to grow 3–5× beyond it, with the same assay. Passive data
must still be quantitatively ambiguous (SVR-001). Design-time analysis showed:

1. **Logistic growth cannot do this.** Logistic deceleration begins at $K/2$, while
   a saturating assay produces an abrupt corner. With a trustworthy Condition A, a
   model-free 15-NN classifier separates the passive curves at ≈ 0.82–0.90 accuracy
   across design-time runs.
2. **A known, fixed saturation scale cannot do this.** Condition A's observed
   plateau sits at ≤ 0.86 S and Condition B's at ≈ S, so plateau level separates
   them perfectly (ceiling 1.00).

## Decision

1. **Matched sharpness.** Growth is Richards with $\nu = 8$. The assay is
   $f(x) = x[1+(x/S)^n]^{-1/n}$ with $n = \nu = 8$. Then the observed passive curve
   in both conditions is *exactly* a Richards curve
   ([DESIGN §5.4](../DESIGN.md#54-passive-family-equivalence-key-result)), and the
   condition affects only the apparent plateau $K'$.
2. **Unknown, variable saturation scale.** $\log S \sim U[\log 0.5, \log 2.0]$ per
   episode, independent of the condition, and never disclosed to the agent. This
   reflects a fact: the linear range depends on instrument, path length and sample
   (A-003).
3. **Scenario selection.** Condition A's carrying capacity is placed at
   $0.80$–$0.90\,S$, near the top of the useful region. This is labelled a DESIGN
   DECISION (A-018), not a biological claim.

The design-time analytic passive ceiling is ≈ 0.58 (0.577) against the SVR-001
threshold of 0.65.

**The construction is a region, not a point.** In the design-time reference
(`experiments/reference/design_validation_output.txt`), passive 15-NN accuracy stays
at 0.53–0.59 under all of the following:
- $\nu$ = 6–10 with $n = 8$, so exact sharpness matching is not required once noise
  is present;
- noise ×0.5 or ×2;
- $r$ range ×0.8 or ×1.2;
- $X_0$ range ÷2 or ×2.

The binding boundary is Condition-A trustworthiness, which needs $n \gtrsim 7.5$ at
$\kappa \le 0.90$ ($n = 7$ gives 5.4 % compression). Gate 0 re-checks this (G0-G,
[GATE0_SPEC](../GATE0_SPEC.md)).

## Alternatives considered

| Alternative | Result | Why rejected |
|---|---|---|
| Logistic growth + any saturating assay | 15-NN ≈ 0.82–0.90 | Fails SVR-001 with a trustworthy Condition A |
| Fixed $S$ | Ceiling 1.00 | Trivially separable by plateau level |
| $S \in [0.8, 1.25]$ | Ceiling ≈ 0.72 | Fails SVR-001 |
| $S \in [0.6, 1.5]$ | Ceiling ≈ 0.61 | Passes with a thin margin |
| **$S \in [0.5, 2.0]$** | **Ceiling ≈ 0.58** | **Accepted** |
| $S \in [0.4, 2.5]$ | Ceiling ≈ 0.56 | Pre-approved fallback (`scenario-v1.1`) |
| Larger passive noise to hide differences | — | Unrealistic noise; weakens the dilution measurement too |
| Hard clipping assay + abrupt (step) growth stop | — | Non-smooth; knife-edge coincidence; no closed-form equivalence argument |

## Consequences

- Positive: passive ambiguity has an analytic explanation and a quantitative
  ceiling, not just a visual impression. Condition A remains trustworthy.
- Negative: the coincidence $\nu = n$ and the placement of $K_A$ near the
  instrument limit are deliberate constructions and must be disclosed (RISKS R-005).
- Negative: validity thresholds depend on the per-episode $S$, which only the
  evaluator knows. The agent must establish the proportional range empirically, as
  in real practice.
