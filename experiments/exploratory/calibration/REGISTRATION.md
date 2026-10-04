# Registration: calibration of stated probabilities, and the shared s500028-BP miss

**Status:** EXPLORATORY, not confirmatory. This is an analysis of committed records only. It makes no
API calls, runs no new episodes, and rescores nothing. Registered 2026-10-04 (UTC), before any of
the statistics below were computed.

**Disclosure:** before writing this file I read the frozen per-episode records. That includes each
agent's final `p_biomass_above_reading`, its `correct` flag, and the s500028-BP records and
transcripts of both Claude runs, as well as the published summaries (M1–M3, mean Brier) and
OPEN_RULINGS §H. None of the new statistics registered here (binned reliability, Murphy
terms, bootstrap intervals, log loss, ECE, the late-data reference posterior, the noise
probabilities) had been computed when this file was pushed.

## Question

How well calibrated are the agents' final stated probabilities on the strong matrix? What
explains the miss that C1 (Opus) and C2 (Sonnet) share on s500028-BP?

## Inputs (read-only; the SHA-256 of every file is recorded in `inputs.json` at analysis time)

| Agent | Run directory under `experiments/results/` |
|---|---|
| C1 Claude Opus 5.5 (`claude-opus-5-5`, effort high, prompt-v2) | `20261003-2323_claude_strong` |
| C2 Claude Sonnet 5.5 (`claude-sonnet-5-5`, effort high, prompt-v2) | `20261004-0049_claude_strong` |
| GoodScientist | `20261003-2333_good_scientist_strong` |
| PassiveBayes | `20261003-2333_passive_bayes_strong` |

- Matrix: strong, seeds 500000–500029 (15 BP, 15 MA), with one record per (seed, agent). No
  dev seeds are used and there are no new runs.
- Reference: `experiments/results/gate0/summary.json` (G0-A PassiveBayes balanced accuracy on
  the 1,000-per-condition test block; G0-B maximum BP compression;
  `diagnostic_dilution.R_BP_p99` / `R_MA_p1`). It is quoted, never recomputed.
- Scenario: `experiments/configs/scenario_v1.json` (read-only), used for the prior ranges and
  noise model in the reference posterior.
- Per-episode Brier is taken from `scores.brier` in each record. The analysis asserts that
  mean Brier equals each run's `summary.json` O1 value to 1e-12. It does not replace that value.

## Forecast and outcome

- Forecast p = `diagnosis.p_biomass_above_reading` (the final submitted value; no agent called
  `declare_state` in a way that changes this).
- Outcome y = 1 if the hidden condition is MEASUREMENT_ARTIFACT, else 0 (the evaluator's
  definition of the Brier truth).
- All 120 records have status `DIAGNOSED`. If any were not, it would be excluded from the
  calibration statistics and reported as such.

## Metrics (per agent, n = 30)

1. **Reliability diagram.** Fixed bins with edges `[0, 0.1, 0.3, 0.7, 0.9, 1.0]`. They are
   left-closed and the last bin is closed, so p = 0.9 goes in the top bin. Each bin shows its
   observed MA frequency against its mean p, with a Wilson 95% interval for the frequency. The
   raw (p, y) points are plotted jittered underneath. The edges are coarse because n = 30 and
   the forecasts cluster near 0, 0.5 and 1.
2. **Murphy decomposition** of Brier over the same bins:
   REL = Σ n_b/N (p̄_b − ō_b)², RES = Σ n_b/N (ō_b − ō)², UNC = ō(1 − ō). The residual
   BS − (REL − RES + UNC) is the within-bin term and is reported, not hidden.
   *Sensitivity:* the same decomposition with one bin per distinct forecast value, where the
   decomposition is exact.
3. **Bootstrap 95% intervals.** These are percentile intervals from B = 10,000 resamples,
   stratified by condition (15 BP and 15 MA drawn with replacement, matching the fixed design),
   using `numpy.random.default_rng(20261004)`. The same resample indices are used for every
   agent, so paired differences are available. Because the design is stratified, UNC = 0.25 in
   every resample.
4. **Secondary measures.** Log loss (natural log, p clipped to [1e-6, 1 − 1e-6], reporting
   the number clipped) and ECE = Σ n_b/N |p̄_b − ō_b| on the same bins. Both get the same
   bootstrap.
5. **By hidden condition.** For BP and MA separately: mean p, mean Brier, mean log loss and
   calibration-in-the-large (mean p − y), with a bootstrap within the condition.
6. **s500028-BP case study.**
   - The passive data, every dilution reading by every agent, and the corrected values (d × reading).
   - Distance from the decision boundary, for each of the 15 BP episodes:
     - k_ratio;
     - the noise-free gap K / f(K) − 1, from the record's hidden config, read only and
       used for diagnostics;
     - GoodScientist's committed ratio R = 10·mean(1:10 reads) / mean(passive 15–18 h)
       against τ = 1.5, and the gap in log(R/τ);
     - each Claude run's own late corrected/plateau ratio (mean over its late-window diluted
       reads of d × reading, divided by the mean passive reading at 15–18 h);
     - PassiveBayes p.
     Gate 0 R_BP_p99 and R_MA_p1 are quoted as the population reference.
   - The reference posteriors:
     (a) the PassiveBayes p committed in the record, which is the simulator-derived passive-only
     posterior;
     (b) a **late-data reference posterior** P(MA | data), computed exactly on a grid from the
     scenario-v1 generative model. The model is S ~ log-uniform(0.5, 2); K = κS with κ ~ U(0.8,
     0.9) under BP or λ ~ U(3, 5) under MA; prior P(MA) = 0.5; reading ~ N(f(K/d),
     (0.003 + 0.02 f)²). It uses every passive or agent reading taken at t ≥ 14 h, where the
     Richards curve is at K to within 2.1e-4 (relative) over the whole prior; this was checked
     on a grid of prior corners before registration. The grid is 4,000 log-S points × 400
     ratio points per condition. Readings before 14 h are not used, and the number dropped is
     reported. As a sanity check, the passive-only version of (b) is compared with
     PassiveBayes p on all 30 episodes (descriptive only).
     (b) is computed separately on each agent's own readings.
   - Noise probability: under the true s500028 config, the probability (Monte Carlo, 200,000
     draws, `default_rng(28)`) that the agent's own measurement design yields a late
     corrected/plateau ratio at least as large as the one it observed. The passive plateau
     readings are re-drawn too.
   - Quotes from both Claude runs' final rationale and any visible text in their transcripts
     (thinking blocks are signed and empty in the records; this is noted, not inferred).
7. **PassiveBayes "lucky" analysis.** Confidence c = max(p, 1 − p) on its correct episodes
   (expected 20) and its wrong ones (expected 10): mean, median and range; the AUROC of c for
   separating correct from wrong (bootstrap interval); the expected number correct under its
   own probabilities, Σ c_i, with the Poisson-binomial probability of ≥ the observed k; and
   the Gate 0 G0-A balanced accuracy (0.567 on 1,000/condition) quoted alongside 20/30
   [Wilson].

## Hypotheses (exploratory)

- **H-a.** C1 and C2 have high resolution (RES near UNC). Their reliability term comes mostly
  from (i) hedged BP forecasts (p ≈ 0.05–0.15 where the BP frequency is 0) and (ii) the
  confident s500028 miss.
- **H-b.** The s500028 miss is *not* a reasonable condition call under measurement noise.
  Given each Claude run's own readings, the late-data reference posterior puts P(MA) near 0,
  and the corrected/plateau ratio is far below τ. The miss comes from answering the literal
  question: true biomass is a few percent above the undiluted reading in every BP culture
  (OPEN_RULINGS §H), and here upward noise in the dilutions enlarged that gap.
- **H-c.** PassiveBayes confidence on its correct answers is not meaningfully higher than on
  its wrong ones, apart from a few extreme passive histories.

## Decision rules (fixed now)

- **D1. Agent differences.** Two agents are said to differ on a metric (Brier, log loss, REL,
  RES, ECE) only if the paired stratified-bootstrap 95% interval of the difference excludes 0.
  Otherwise the result is "no detectable difference at n = 30". No significance language
  (EXPERIMENT_PLAN §10).
- **D2. Condition bias.** An agent is "biased toward MA on BP" or "biased toward BP on MA" if the
  bootstrap interval of calibration-in-the-large in that condition excludes 0.
- **D3. s500028 call.** The miss is a "reasonable call under measurement noise" for an agent if
  either:
  - (i) its late-data reference posterior P(MA | own data) ≥ 0.2; or
  - (ii) its corrected/plateau ratio ≥ τ = 1.5; or
  - (iii) the noise probability ≥ 0.05 that the BP truth produces a ratio as large as one that
    would cross τ.
  It is "not a reasonable condition call" if the posterior is < 0.01 AND the ratio is < τ.
  Anything in between is "borderline". Separately, the analysis says whether the *literal*
  claim "biomass higher than the undiluted reading" was true for this culture (noise-free gap
  > 0).
- **D4. PassiveBayes confidence.** Its confidence is called "informative about correctness" if
  the bootstrap AUROC interval excludes 0.5. Otherwise it is "no detectable information".

## Spend cap and procedure

- Spend cap: **$0**. No Anthropic API call is made. There is no dry run, because no episodes
  are run.
- Each (seed, configuration) record is used exactly once. No record is rescored, rewritten or
  copied into a results tree. s500028-BP stays scored as committed (correct = false).
- All outputs go in `experiments/exploratory/calibration/`. Tests for the new driver logic go
  in `tests/exploratory/calibration/`. No change to `src/`.
- Deviations from this registration will be added below in a dated **Deviations** section.

## Deviations

**2026-10-04 (after the analysis was run; nothing above was edited).**

1. Input hashes are written to `inputs.json` as registered. They are also copied into
   `results.json` under `inputs_sha256`.
2. Added, as descriptive and unregistered: for each s500028 dilution reading, the z-score
   against the noise-free reading of the true culture, z = (y − f(K/d)) / (σ_abs + σ_rel·f(K/d)),
   and the share of each agent's mean Brier that comes from s500028. Neither feeds a decision rule.
3. No episodes were run, so this directory contains no new `usage.jsonl`, run records or
   `summarize` outputs. The committed per-run `summary.json` / `results.md` in
   `experiments/results/<run>/` are the per-run summaries; they are cited by path and hashed,
   not regenerated (regenerating them would re-derive frozen results).
4. The exact (one bin per distinct forecast) Murphy sensitivity turns out to be degenerate:
   almost every forecast value is attained by episodes of a single condition, so REL = Brier and
   RES = UNC for every agent. It is reported in `results.json` but carries no information.
5. Where the registration says "bootstrap within the condition" (§5), the within-condition
   intervals are taken from the same stratified resamples as everything else (each condition is
   one stratum), so no separate resampling was done.
