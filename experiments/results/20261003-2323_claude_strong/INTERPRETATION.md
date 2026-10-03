# Interpretation note: C1 Claude, strong matrix (DEV-014/015)

Run `20261003-2323_claude_strong`: `claude-opus-5-5`, effort `high`, prompt-v2,
eval seeds 500,000–500,029 (15 BP, 15 MA), at most 12 turns, budget 6. Baselines
`20261003-2333_good_scientist_strong` and `20261003-2333_passive_bayes_strong` used the same matrix.
All numbers below are taken from `summary.json`, `results.md` and the episode records in this
directory. The "minimal" matrix (MS3, seeds 500,000–500,009) is the first ten of these episodes.

## Result

- Claude got M1 29/30, M2 30/30 and M3 29/30. Every episode was `DIAGNOSED`, with no
  `API_FAILURE`, no `REFUSED` and no re-runs, so intention-to-treat equals primary.
- Baselines: GoodScientist 30/30 on M1–M3, PassiveBayes M1 20/30 and M2 = M3 = 0/30.
- The diagnostic behaviour (H2) is present: in every episode Claude diluted a late aliquot
  that is in the frozen diagnostic set D_diag. In all 15 MA episodes, its late-biomass estimate
  was within 5% of the true K.
- Efficiency: Claude used 5.8 of its 6 budget units on average, against 3 for GoodScientist.
  It never called `declare_state`.

## The single miss (s500028-BP)

Claude answered `BIOMASS_ABOVE_READING` (p = 0.80) in a BP episode. Its dilutions at 18 h gave
about 1.47, while the undiluted readings were about 1.34 and the true K was 1.407. M2 was
satisfied, so the miss counts against M1 and M3 only.

This exposes a residual property of the assay, not an agent-side bug. Because
f(x) = x[1+(x/S)^n]^(-1/n) is compressive below S as well, true BP biomass is also above the
undiluted reading, by 2.3–4.0% in the 15 BP episodes here (K/S between 0.82 and 0.88). So
prompt-v2's question, "at the level the undiluted readings indicate, or higher", has a small
literal gap in BP. MA gaps are many-fold. Claude's two 18 h dilutions overshot the true value
(about +4.5%), which made a ~4% gap look like ~10%.

The scoring is pre-registered and is **not** changed after seeing results. This is recorded for
Arnav in OPEN_RULINGS §H as a candidate for a future prompt revision. It does not apply to this
run.

## Cost

There were 136 API calls: 415,386 input tokens and 42,592 output tokens, with no cache use and
no errors (`usage.jsonl`, token counts only). Every call stopped with `tool_use`.

## Limitations

- There are 30 episodes, so the Wilson intervals are wide (M1 [0.83, 0.99]).
- The model is a single one (C1), with no second model.
- The rulings are provisional, decided by Ben and pending Arnav (OPEN_RULINGS §F).
- The benchmark and its scoring are ours, so this measures the stated task in a simulated lab.
  It does not measure general scientific ability.
