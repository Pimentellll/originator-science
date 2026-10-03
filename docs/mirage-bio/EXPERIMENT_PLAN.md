# MIRAGE-Bio — Experiment Plan

| Field | Value |
|---|---|
| Status | Pre-registered for MVP (3 October 2026). No experiments have been run. |
| Role | **How we measure**: matrices, metrics, reporting, interpretation, claims |
| Related | [ANALYSIS §14–15](ANALYSIS.md#14-metrics) · [DESIGN §15–16](DESIGN.md#15-evaluation) · [GATE0_SPEC](GATE0_SPEC.md) · [BENCHMARK_METHODOLOGY](../BENCHMARK_METHODOLOGY.md) · [RISKS](RISKS.md) |

This plan is fixed before any evaluation episode is run. Changing it after seeing
evaluation results must be recorded as a deviation in the results report.

---

## 1. Research question

In the MIRAGE-Bio `scenario-v1` environment, where passive OD readings cannot
reliably distinguish a true biological plateau from a measurement-produced one,
does an autonomous AI scientist (Claude Opus 5.5):

1. choose a diagnostic control (a late-stage diluted measurement whose dilution
   factor Gate 0 demonstrated to distinguish the worlds),
2. reach the correct diagnosis, and
3. do both within the experimental budget?

### 1.1 Two separate phases

| Phase | What it validates | When | Who decides |
|---|---|---|---|
| **Scientific benchmark construction** | The *environment*: passive ambiguity, Condition-A trustworthiness, diagnostic separation, undiluted and early interventions non-diagnostic, frozen diagnostic dilution set $D_{\text{diag}}$, nuisance independence | Gate 0 ([GATE0_SPEC](GATE0_SPEC.md)), before any agent run | Pre-registered thresholds only |
| **Agent experiment** | The *agent's behaviour* in the frozen environment | Only after the scenario configuration is frozen and hashed | This plan |

Once Gate 0 freezes the parameters, **Claude's outcomes must never be used to
retune the benchmark** (ANALYSIS ER-007; DEVELOPMENT_PLAN stop rule 16). Changing
parameters, thresholds, the diagnostic set $D_{\text{diag}}$, the diagnostic-control rule or the prompt to make the result "more
interesting" would contaminate the evaluation.

- If the benchmark turns out easy for Claude, report that.
- If Claude fails, report that.
- A genuine environment bug found after agent runs is fixed under a **new** scenario
  version, with a full Gate 0 re-run and a full re-run of all agents. The original
  results and the reason are retained and reported.

## 2. Hypotheses

Narrow, about this environment only.

| ID | Hypothesis | Evidence that supports it | Evidence against it |
|---|---|---|---|
| H1 (environment check) | The passive information ceiling holds and the task is solvable. | On the evaluation episodes and on the 1,000-per-condition reference, `PassiveBayes` M1 ≤ 0.65 and `GoodScientist` M3 ≥ 0.95. | Either fails. The environment is then invalid and H2/H3 are not evaluated. |
| H2 (primary) | Claude's justified accuracy exceeds the passive-ambiguity threshold (0.65), which lies above the analytic passive ceiling (≈ 0.58). | Wilson 95 % lower bound of Claude M3 > 0.65. | Upper bound < 0.65. An interval containing 0.65 is **inconclusive**. |
| H3 (descriptive) | When Claude performs a diagnostic control, it interprets it correctly. | Conditional accuracy (correct given a diagnostic control) reported with Wilson interval. | No threshold; reported descriptively. |

H1 is a precondition, not a finding about the agent. With 10–30 episodes, H2 can be
supported only if performance is clearly high. A null or inconclusive result is
reported as such.

## 3. Experimental units

One **episode** is one seeded hidden scenario `(seed, condition)` run once by one
agent configuration. Episodes are independent: there is no memory across
episodes, and each episode starts a new conversation.

## 4. Conditions

Two hidden conditions only: `BIOLOGICAL_PLATEAU` and `MEASUREMENT_ARTIFACT`
([DESIGN §6](DESIGN.md#6-hidden-conditions)). Matrices are balanced and
interleaved (ER-001): even seed offsets are `BIOLOGICAL_PLATEAU` and odd offsets are
`MEASUREMENT_ARTIFACT`.

## 5. Agent configurations

| ID | Configuration | When |
|---|---|---|
| C1 (primary) | Claude adapter: `claude-opus-5-5`, effort `high`, adaptive thinking (model default), `prompt-v1` (minimal; no hypothesis scaffolding; `declare_state` optional), ≤ 12 turns, budget 6, no model fallback | MVP |
| B1 | `GoodScientist` (DESIGN §16.1) | MVP |
| B2 | `PassiveBayes` (DESIGN §16.2) | MVP |
| C2 | One additional configuration (another model or effort level) on the same matrix and prompt | **Phase 2 only**, after MS4 is frozen ([DEVELOPMENT_PLAN §9](DEVELOPMENT_PLAN.md#9-expansion-plan)) |

## 6. Seeds and repetitions

| Matrix | Seeds | Episodes | Use |
|---|---|---|---|
| Development | `dev` block 0–9,999 | as needed | Prompt debugging (MS2) only. Never reported as results. |
| **Minimal** | 500,000–500,009 | 10 (5 BP, 5 MA) | MS3 first empirical result |
| **Strong** | 500,000–500,029 | 30 (15 BP, 15 MA) | MS4 final result; the minimal matrix is its prefix |
| Baseline reference | Gate 0 test seeds 900,000–900,999 | 1,000 per condition | Precise baseline values (B1, B2) |
| Demo | `demo_pair.json` (2 episodes) | 2 | Demo only. Never in metrics. |

- Each (seed, configuration) is run **once**. An `API_FAILURE` episode is re-run once
  with the same seed. The second outcome is final and both are retained.
- Baselines B1 and B2 are run on exactly the same evaluation episodes as C1, plus
  the reference block.
- Matrices are defined in `experiments/configs/eval_matrix_v1.json` and hashed in
  each run manifest.

## 7. Metrics, baselines and data retention

### 7.1 Primary metrics

Exactly as defined in [ANALYSIS §14](ANALYSIS.md#14-metrics) and computed as in
[DESIGN §15](DESIGN.md#15-evaluation):

| ID | Metric | Reported as |
|---|---|---|
| M1 | Diagnosis accuracy | k/n, Wilson 95 %, overall and per condition |
| M2 | Diagnostic-control rate | k/n, Wilson 95 %, overall and per condition |
| M3 | Justified accuracy | k/n, Wilson 95 %, overall and per condition |
| M4 | Experimental cost | mean, median, max replicate-readings |
| Q1 (secondary, descriptive) | Quantitative reconstruction adequacy | k/n per condition; not part of M3 |
| M5 (stretch, non-blocking) | Experiment diagnosticity | mean of max matched-twin $D(a)$ per episode ([BENCHMARK_METHODOLOGY §3](../BENCHMARK_METHODOLOGY.md#3-experiment-diagnosticity)); reported only if implemented |
| O1 (optional) | Brier score | mean over diagnosed episodes |
| O2 (optional) | Rounds to diagnosis | mean `measure_calls_before_diagnosis` |

Descriptive secondary outputs (not metrics): reasons controls were invalid (from the
audit); relative error of `late_biomass_estimate_od` against $X(18)$; episode status
counts.

### 7.2 Baselines

| Baseline | Expected (design-time) | Role |
|---|---|---|
| B1 `GoodScientist` | M1 ≈ 1.00, M2 = 1.00, M3 ≈ 1.00, M4 = 3 | Demonstrates solvability within budget; validates the evaluator |
| B2 `PassiveBayes` | M1 ≈ 0.57, M2 = M3 = M4 = 0 | Strongest implemented passive baseline; uses knowledge of the prior that the LLM lacks. The bound on passive strategies is the analytic ceiling (≈ 0.58) from Gate 0, not this classifier. |

On a 30-episode matrix B2's M1 will fluctuate (±≈ 0.09). The 1,000-per-condition
reference value is the one to compare against.

### 7.3 Data retention

- Every evaluation episode record is committed under
  `experiments/results/<run_id>/episodes/`, including failures. Records include the
  full LLM transcript.
- `manifest.json` records: agent configuration, prompt version, model, effort,
  matrix file and hash, scenario hash, start and end times, re-run mapping.
- Records are never edited or deleted. A correction means a new run directory, and
  the reason is noted in the results report.
- Development runs stay in `.local/runs/` unless deliberately committed.
- No credentials are stored. Request logs exclude headers.

## 8. Statistical reporting

- Report **exact counts** (k/n) and proportions for M1–M3, overall and per
  condition. Report M4 as mean, median and max.
- Report **Wilson score 95 % intervals** for proportions ($z = 1.96$):

$$\frac{\hat p + \frac{z^2}{2n}}{1 + \frac{z^2}{n}} \pm \frac{z}{1 + \frac{z^2}{n}}\sqrt{\frac{\hat p(1-\hat p)}{n} + \frac{z^2}{4n^2}}$$

  Example: 8/10 gives [0.49, 0.94]; 27/30 gives [0.74, 0.97].
- Report the primary denominator and the intention-to-treat variant (failures
  counted as incorrect) side by side when any `API_FAILURE` or `REFUSED` occurs.
- **No significance testing is the headline.** With n ≤ 30, intervals are wide.
  H2 is judged only by the pre-declared Wilson-bound rule (§2).
- No subgroup analysis beyond the two conditions. No post-hoc metric definitions.
- All tables are generated from records by `summarize`. No hand-typed numbers.

Results table template (`results.md`):

| Agent | n | M1 | M2 | M3 | M4 mean | Status issues |
|---|---|---|---|---|---|---|
| C1 Claude | k/n [lo, hi] | k/n [lo, hi] | k/n [lo, hi] | k/n [lo, hi] | x.x | counts |
| B1 GoodScientist | … | … | … | … | 3.0 | 0 |
| B2 PassiveBayes | … | … | 0/n | 0/n | 0.0 | 0 |

The same table is repeated per condition.

## 9. Interpretation matrix

| Observation | Interpretation | Action / reporting |
|---|---|---|
| B2 M1 > 0.65 on the reference set, or T-016 fails | Passive ambiguity broken; environment invalid | **Stop.** Do not report LLM results as evidence. Investigate (R-002). |
| B1 M3 < 0.95 | Evaluator, environment or dilution design broken | **Stop.** Fix before any LLM claim (R-003). |
| C1 M3 high (Wilson lower bound > 0.65) | In this scenario Claude selects and correctly interprets the decisive control | Report as support for H2, with the caveat that the control is textbook practice (R-007). No generalisation. |
| C1 M1 high but M3 low | Correct answers without diagnostic evidence: guessing, prior knowledge, or non-diagnostic measurements | Report as *unjustified accuracy*. Show audit reasons. |
| C1 M2 high but M1 low | Right experiment, wrong interpretation (e.g. forgot back-correction, misread the ratio) | Report as an interpretation failure. Show examples via replay. |
| C1 M1 ≈ passive level and M2 low | Accepts readings at face value; does not recognise the ambiguity | Report as failure to recognise ambiguity. This is a legitimate negative result. |
| C1 M2 high but Q1 low | Diagnostic but quantitatively poor experiments (e.g. late 1:2 dilutions) | Report. Justified accuracy is unaffected; Q1 per condition shows reconstruction quality. |
| C1 high M4 with high M3 | Solves the task but spends budget inefficiently | Efficiency note only. |
| Wilson interval for C1 M3 contains 0.65 | Inconclusive at this sample size | Report as inconclusive. Do not round up to "works". |
| The benchmark proves easy (or hard) for Claude | A property of this agent in this frozen environment | Report it. **Never** retune parameters, thresholds or prompt in response (§1.1). |
| C1 diagnoses correctly after a late 1:2 dilution only | Diagnostic evidence that is quantitatively inaccurate (GATE0_SPEC §6) | Counts toward M1, M2 and M3 (subject to the frozen $D_{\text{diag}}$); Q1 = no. Report the count. |
| API failures or refusals > 20 % of episodes | Results incomplete | Report the ITT variant prominently. State the failure cause. Do not silently replace episodes. |
| C1 refusals concentrated in one condition | Possible content-triggered classifier behaviour | Report as an observation about the deployment surface, not about scientific reasoning. |

## 10. Claims

### Allowed (if supported by the committed results)

- "In MIRAGE-Bio `scenario-v1`, a classifier with full knowledge of the simulator,
  using passive data only, reaches X accuracy (ceiling Y)."
- "One adequately diluted late-stage measurement separates the two hidden conditions
  (`GoodScientist` M3 = …)."
- "On n evaluation episodes, Claude Opus 5.5 (effort high, prompt-v1) achieved
  justified accuracy k/n [Wilson 95 % CI], diagnostic-control rate …, at mean cost …"
- "Failures were of type … (audit breakdown)."
- "The environment, evaluator and every reported number are reproducible from the
  committed configuration and records."

### Forbidden

- Any claim about real bacteria, real plate readers, or a real OD threshold.
- "Claude can do science", "AI scientists recognise ambiguity", or any claim beyond
  this scenario, configuration and sample.
- Claims of statistical significance from these sample sizes.
- Comparisons with other models that were not run on the same matrix.
- Describing the demo episode as representative performance. The results table is
  the claim.
- Describing the agent method as novel.
- Presenting LLM runs as seed-reproducible (only transcripts are).
- Calling `PassiveBayes` (or any implemented classifier) optimal.
- Claiming a U-shaped dilution optimum for discrimination that Gate 0 does not show.
- Calling MIRAGE or MIRAGE-Bio the "first" of anything
  ([DIFFERENTIATION §7](../DIFFERENTIATION.md#7-novelty-boundary)).

## 11. Run procedure (checklist)

1. Confirm Gate 0 passed and `scenario_sha256` matches
   `experiments/results/gate0/summary.json`. From this point the scenario is frozen
   (§1.1).
2. Confirm `prompt_version = prompt-v1` is frozen. Note the model, effort and SDK
   version.
3. Run B1 and B2 on the matrix and the reference block. Check that H1 holds before
   running C1.
4. Run C1 on the minimal matrix (MS3), then extend to the strong matrix (MS4).
   Interleaving preserves balance at any stopping point.
5. Re-run `API_FAILURE` episodes once. Record the mapping in the manifest.
6. Run `summarize`. Commit records, `summary.json`, `results.md` and `results.png`.
7. Write a ≤ 1-page interpretation using §9 and claims using §10. The science lead
   signs off before anything is put on slides.
