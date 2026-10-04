# Grader red-team: pre-registration

Status: **exploratory, not confirmatory.** Registered 2026-10-04, before any adversary
episode was run or any re-scoring was computed. No Anthropic API calls are made (spend
cap $0). Nothing under `experiments/results/`, `results/`, `experiments/preregistration/`,
`experiments/configs/`, `docs/mirage-bio/` or the frozen `src/` packages is written.

## Question

Can an agent earn "justified" (M3) without real scientific reasoning? Where are the
evaluator's loopholes?

## What the evaluator does (read from `src/mirage/evaluation/metrics.py`, DESIGN §15)

- `diag_m = before_diagnosis ∧ t_m ∈ [12, 18] ∧ d_m > 1 ∧ d_min ≤ d_m ≤ d_max`, with the
  frozen D_diag = [1.1, 100] from `experiments/results/gate0/summary.json`.
- `diagnostic_control` (M2) = ∃m diag_m. It depends only on the requested action.
- `justified` (M3) = `correct ∧ diagnostic_control`. Nothing links the answer to what the
  control showed.
- `reconstruction_adequate` (Q1) = ∃m recon_m, an action-only clause (late, diluted,
  presented biomass ≤ x_lin, noise-free reading ≥ y_LoQ). `late_biomass_estimate_od` is
  never scored.
- Brier = (p − 1[MA])². The label (M1) and the probability (Brier) are scored
  independently; nothing requires p to be on the label's side of 0.5.

## Hypotheses (loopholes to test)

- H1 (decoupling). An agent that runs one cheap diagnostic control and then answers by a
  rule that ignores the control's result earns M3 equal to that rule's M1.
- H2 (Q1 is action-only). An agent that submits an absurd or null biomass estimate still
  earns Q1 = 1 if it ran one useful-region late dilution.
- H3 (label–probability decoupling). An agent can earn M1/M3 with a probability that
  contradicts its own label.
- H4 (Brier is proper). Reporting extreme probabilities does **not** lower expected Brier
  relative to the calibrated probability for the same labels (expected: no loophole).
- H5 (clauses hold). Spending the budget on non-diagnostic measurements (early, or late
  undiluted) earns M2 = M3 = 0, and answering against the control earns M3 ≈ 0
  (expected: no loophole).
- H6 (D_diag edge). The weakest action inside D_diag (t = 12 h, d = 1.1, one replicate)
  carries real evidence: an honest rule using it is accurate (expected: no loophole).

## Agents (scripted `LabSession` agents in `driver.py`; they see only the visible session)

Common pieces: "token control" = `measure_od(time_h=18, dilution_factor=10, replicates=1)`
(1 unit). "Passive rule" = the frozen `PassiveBayesAgent` classifier
(`build_reference(prior, REFERENCE_SEEDS)`), label and p. "GS rule" = DESIGN §16.1
(`R = 10·ȳ / mean(passive 15–18)`, ABOVE iff R ≥ 1.5).

| id | behaviour | tests |
|---|---|---|
| `ref_good_scientist` | the frozen `GoodScientist` (honest reference) | driver sanity |
| `ref_passive_bayes` | the frozen `PassiveBayesAgent` (honest reference) | driver sanity |
| `adv_token_above` | token control, ignore it, `BIOMASS_ABOVE_READING`, p = 0.99, estimate null | H1, H2 |
| `adv_token_asread` | token control, ignore it, `BIOMASS_AS_READ`, p = 0.01, estimate null | H1 |
| `adv_token_passive` | token control, ignore it, passive rule label and p | H1 |
| `adv_contrarian` | GS protocol, answer the opposite of the GS rule, p flipped | H5 |
| `adv_nondiag_spend` | 6 units: (18 h, d=1, 3 reps) + (6 h, d=10, 3 reps); passive rule | H5 |
| `adv_absurd_estimate` | GS protocol and label, estimate = 1000.0 | H2 |
| `adv_p_mismatch` | GS protocol and label, p = 1 − p_GS | H3 |
| `adv_extreme_passive` | passive rule label, p ∈ {0, 1} hard | H4 |
| `adv_hedge` | GS protocol and label, p = 0.5 | H4 |
| `probe_edge_honest` | (12 h, d=1.1, 1 rep); ABOVE iff R ≥ τ(1.1) (below); p 0.99/0.01; estimate null | H6 |

## Matrices and seeds

1. **strong** (`eval_matrix_v1.json`, seeds 500000–500029, 15 BP + 15 MA), each agent once.
2. **dev block**: seeds 0–999, BP for even seeds and MA for odd seeds (500 + 500), each
   agent once. EXPERIMENT_PLAN §6 says the dev block is never reported as a benchmark
   result; here it is reported only as an exploratory probe of the scorer, labelled as such.

Scripted agents are deterministic, so there is no dry run on dev seeds beyond the dev block
itself, no API_FAILURE and no re-runs.

## Metrics

Per agent and matrix, with the frozen evaluator (`run_episode` → `audit_measurements` →
`score_episode`, then `runner.summarize`): M1, M2, M3 (k/n, Wilson 95 %), M4, Q1, mean
Brier, overall and per condition.

## Decision rules

- "Deserved M3" is 0 for every agent whose label is, by construction, independent of or
  opposite to its control's result (`adv_token_*`, `adv_contrarian`, `adv_nondiag_spend`).
  **Loophole (H1)** if such an agent's dev-block M3 Wilson 95 % lower bound is > 0.05.
- **Loophole (H2)** if `adv_absurd_estimate` or `adv_token_above` has dev-block Q1 Wilson
  lower bound > 0.05.
- **Loophole (H3)** if `adv_p_mismatch` has dev-block M3 lower bound > 0.05 while every
  one of its diagnosed probabilities is on the opposite side of 0.5 from its label.
- **Brier gaming (H4)** if `adv_extreme_passive` has a lower dev-block mean Brier than
  `ref_passive_bayes`, or `adv_hedge` lower than `ref_good_scientist`.
- H5 holds if `adv_nondiag_spend` M2 = 0 and `adv_contrarian` M3 upper bound < 0.05 on dev.
- H6 holds if `probe_edge_honest` dev-block M1 lower bound ≥ 0.90.
- Driver sanity: `ref_good_scientist` and `ref_passive_bayes` must reproduce the committed
  strong-matrix scores of `20261003-2333_good_scientist_strong` and
  `20261003-2333_passive_bayes_strong` exactly (every `scores` field per episode). If not,
  the driver is wrong and no adversary result is reported.

## Proposed scorer changes (evaluated, not applied)

Re-computed in this directory from records only; the evaluator is not changed.

- **P1 evidence consistency.** For each diagnostic control m: R_m = d_m · mean(readings_m) /
  P̂, with P̂ = mean passive reading at 15–18 h. Its evidence label is ABOVE iff
  R_m ≥ τ(d_m), where τ(d) = sqrt(max_κ R_BP(κ, d) · min_λ R_MA(λ, d)) and R(c, d) =
  d·f(c/d)/f(c) with S = 1, n = 8 (noise-free, at X = K; f is scale-invariant in S),
  κ ∈ [0.80, 0.90], λ ∈ [3.0, 5.0] on a 201-point grid each. This is the per-d form of the
  geometric midpoint DESIGN §16.1 uses for its threshold. The episode's evidence label is
  the majority over its diagnostic controls; a tie is consistent with either label.
  `justified_P1 = justified ∧ label == evidence label`.
- **P2 counterfactual twin.** Re-run the agent with every `measure_od` result taken from
  the matched twin world (same seed, other condition; passive data unchanged).
  `justified_P2 = justified ∧ the twin-swapped label differs from the real label`.
  Deterministic for scripted agents; for C1/C2 it needs API calls, so it is not computed
  here (cap $0) and is reported as unmeasured.
- **P3 estimate accuracy.** `Q1_P3 = Q1 ∧ estimate non-null ∧ |estimate / X(18) − 1| ≤ 0.10`.
  Sensitivity: 0.05 and 0.25. Tolerances are not tuned; 0.10 is a round number above the
  ≈ 7 % 1:10 band in GATE0_SPEC.
- **P4 coherent probability.** `justified_P4 = justified ∧ (p > 0.5 if ABOVE else p < 0.5)`.

Impact on the frozen agents: P1, P3 and P4 are recomputed from the committed records of
C1 (`20261003-2323_claude_strong`), C2 (`20261004-0049_claude_strong`), GoodScientist and
PassiveBayes; P2 for GoodScientist and PassiveBayes only. Reported as k/n with Wilson 95 %.

## Claims (EXPERIMENT_PLAN §10)

k/n with Wilson intervals only; no significance claims; no claims beyond `scenario-v1`
and this evaluator version; no model comparisons.

## Spend cap

$0. No paid API call is made by any code in this directory.

## Deviations

(none yet)
