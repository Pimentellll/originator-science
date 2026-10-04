# Exploratory registration: measurement-price sensitivity (cost-sensitivity)

| Field | Value |
|---|---|
| Status | **Exploratory, not confirmatory.** Registered before any paid API call and before any result was computed. |
| Branch | `exp/cost-sensitivity` (off `origin/main` at `d56cb1a`) |
| Registered | 2026-10 session of the 5-session parallel lab (commit that adds this file) |
| Scope | MIRAGE-Bio `scenario-v1` only. No claim beyond this scenario, model, prompt and matrix. |

## 1. Question

At what measurement price does Claude (Sonnet 5.5, effort high) stop running the
diagnostic control, and does its stated confidence drop when it skips it?

## 2. Hypotheses (descriptive)

- **H-price.** As the price of a dilution replicate rises against a fixed 6-unit budget,
  the diagnostic-control rate (M2) and justified accuracy (M3) fall.
- **H-confidence.** In episodes where no diagnostic control is run, the stated confidence
  `max(p, 1 - p)` is lower than in episodes where it is run.
- **H-lucky.** Higher prices raise the number of correct-but-unjustified answers
  (M1 without M3, "lucky-correct").

These are expectations, not commitments. Any outcome, including no change, is reported.

## 3. Design: change only the price

How cost is defined today (read, not edited): `src/mirage/lab/tools.py` has
`BUDGET_UNITS = 6` and states "each replicate reading costs 1 unit" in three places
(the system prompt, the `measure_od` tool description and the observation's
`budget.cost` string). `src/mirage/lab/environment.py::LabEnvironment._measure`
rejects a request when `replicates > budget_remaining` and otherwise subtracts
`replicates`.

Three ways to vary price were considered:

| Design | What changes | Verdict |
|---|---|---|
| A. `p` units per replicate, budget fixed at 6 units | Only the per-replicate price. Fewer replicates become affordable as a consequence of the price, which is what a price does. | **Chosen.** |
| B. `p` units per replicate, budget scaled to `6p` | Nominal numbers only; the affordable set of experiments is unchanged. Tests number framing, not price. | Rejected. |
| C. Price unchanged, a stated per-unit penalty in the prompt | Adds a new objective that the deterministic evaluator does not score (the penalty would be fictitious) and adds new instruction text. Two manipulations at once. | Rejected. |

Design A is implemented **without editing frozen source**, as driver code in
`experiments/exploratory/cost-sensitivity/`:

- `PricedLabEnvironment(LabEnvironment)` overrides only `_measure`: a request is
  accepted iff `p * replicates <= budget_remaining`, and `p * replicates` units are
  subtracted. Measurement noise streams, the latent model, events, validation and all
  other behaviour are inherited unchanged. At `p = 1` it must be behaviourally identical
  to `LabEnvironment` (tested).
- `PricedClaudeAgent(ClaudeAgent)` changes only the three price strings
  ("costs 1 unit from a budget of 6 units" -> "costs `p` units from a budget of 6 units";
  "costs 1 budget unit" -> "costs `p` budget units"; "1 unit per replicate reading" ->
  "`p` units per replicate reading"). The frozen tool-use loop
  (`ClaudeAgent.run`) is reused unchanged. At `p = 1` the system prompt, tools and first
  message are byte-identical to prompt-v2 (`prompt_sha256` must equal
  `dc07da980883558de995de94ed9c3affc1c8982f31fc5f149f9bfcacda1d91d1`; tested).
- Scoring uses the frozen `audit_measurements` / `score_episode` / `aggregate` and the
  frozen Gate 0 diagnostic action set (`late_window_h = [12, 18]`, `d_min = 1.1`,
  `d_max = 100`, `evaluated_replicates = 1`). **M2 still applies unchanged**: it depends
  only on the time, dilution and order of accepted `measure_od` calls, not on cost, and
  one replicate suffices for a control. A control therefore remains affordable at every
  registered price.
- Note: the evaluator's `M4` (`cost_units`) counts replicate readings. Units spent are
  `p * M4`; both are reported.

## 4. Configurations

All: model `claude-sonnet-5-5` (never substituted), effort `high`, `MAX_TOKENS` 16000,
at most 12 turns, `MAX_REPLICATES` 3, dilution 1-100, budget 6 units, no caching.

| ID | Price per replicate | Max affordable replicates | Prompt |
|---|---|---|---|
| P1 | 1 unit | 6 | prompt-v2, byte-identical (same configuration as C2 except the driver) |
| P3 | 3 units | 2 | prompt-v2 with the three price strings set to 3 |
| P6 | 6 units | 1 | prompt-v2 with the three price strings set to 6 (one replicate affordable) |

## 5. Seeds and run order

- **Dry run (pipeline check only, never reported as results):** development seeds
  0 (BP) at P1, 1 (MA) at P3 and 2 (BP) at P6.
- **Evaluation:** the full `strong` matrix of `experiments/configs/eval_matrix_v1.json`
  (seeds 500000-500029, 15 BP + 15 MA), each episode once per configuration (90
  episodes). Episodes are interleaved: for each seed in matrix order, P1, then P3, then
  P6. Each configuration writes its own run directory.
- An `API_FAILURE` episode is re-run once; both records are kept (runner convention:
  `reruns/<id>.attempt1.json`).
- s500028-BP is scored as the frozen evaluator scores it; it is not rescored
  (OPEN_RULINGS.md).

## 6. Metrics

From the frozen `summarize` (`summary.json`) per configuration: M1, M2, M3 as k/n with
Wilson 95 % intervals (overall and per condition), M4 (replicates), Q1, O1 (mean Brier),
O2, status counts. Derived by `analyze.py` from the episode records:

- units spent = `p * cost_units`;
- lucky-correct = `correct and not diagnostic_control`, k/n with Wilson interval;
- stated confidence `c = max(p_above, 1 - p_above)` and Brier, split by
  control / no control (mean, n);
- count of `measure_od` calls rejected for exceeding the budget.

## 7. Decision rules (fixed now)

1. **Stop price.** Claude "stops running the control" at the lowest registered price
   whose M2 point estimate is <= 0.5 (<= 15/30). If no price meets this, the answer is
   "it did not stop at any tested price up to the one-replicate level (P6)".
2. **Detectable change in M2, M3 or lucky-correct vs P1.** Only if the Wilson 95 %
   intervals do not overlap. Otherwise "no detectable difference at n = 30" (never
   "equal"). No significance tests.
3. **Confidence drop.** Assessed only if at least 3 diagnosed no-control episodes exist
   (pooled across prices; also within a price if that price has >= 3). "Drop" if the mean
   confidence of no-control episodes is at least 0.10 below that of control episodes
   (same price, and pooled). Fewer than 3: listed individually, no conclusion.
4. P1 vs the frozen C2 run (same model, prompt, matrix) is reported descriptively as a
   reproducibility check under rule 2 only.

## 8. Spend cap

- Hard cap: **USD 5.00** of Anthropic API usage for the whole session, dry run included.
- Pricing (public Anthropic pricing page, fetched at registration): Claude Sonnet 5.5
  USD 2 / MTok input, USD 10 / MTok output, USD 2.50 / MTok 5-minute cache write,
  USD 0.20 / MTok cache read.
- Projection from C2 (303k input, 30k output for 30 episodes): about USD 0.91 per
  configuration, about USD 2.7 for the three, plus about USD 0.1 dry run.
- Enforcement: the driver logs every API call's token usage (`usage.jsonl` per run and a
  session ledger) and, before starting an episode, stops if
  `spent + 2 * (largest episode cost so far, at least USD 0.10) > USD 4.75`.
  If the cap stops the run early, the interleaved order keeps the completed prefix
  balanced across configurations; this is reported as a partial result.

## 9. Claims allowed

Per EXPERIMENT_PLAN §10: k/n with Wilson 95 % intervals; no significance claims; no
claims beyond this scenario/configuration/sample; no comparison with models not run on
this matrix. This is an exploratory variant: it does not change C1/C2 results.

## Deviations

(None at registration. Later deviations are appended here with a date.)

- **2026-10-04 (after the runs).** `analyze.py` `write_figure` crashed because a Wilson
  bound at k = n differed from the rate by about 1e-16, which gave a negative error-bar
  length. The error-bar lengths are now clamped at 0. This is a plotting fix only; no
  metric or decision changed.
- **2026-10-04 (after the runs).** RESULT.md has a clearly labelled post-hoc descriptive
  section: the measurements chosen, the true-vs-read gap in the misdiagnosed plateau
  cultures, and confidence on correct vs wrong answers. None of it was registered, and
  none of it is used for a decision.
- No other deviation. Configurations, seeds, order, metrics, decision rules and the
  spend cap were as registered. There were no API failures or re-runs, and the spend
  guard never triggered.
