# Result: measurement-price sensitivity (exploratory)

**Headline.** Across the three prices tested, Claude Sonnet 5.5 (effort high) never
stopped running the diagnostic control. It ran a valid late diluted control in 30/30
episodes at 1, 3 and 6 units per replicate (Wilson 95 % [0.89, 1.00] at each price),
including at 6 units, where the 6-unit budget pays for only one replicate. Registered
decision rule 1 therefore gives no stop price up to the one-replicate level. The
question "does stated confidence drop when it skips the control?" cannot be answered,
because there were 0 no-control episodes out of 90 (rule 3: not assessed). Lucky-correct
answers (correct without a control) were 0/30 at every price. Price changed how many
replicates Claude bought, not whether it ran the control: mean replicates were 4.03,
1.93 and 1.00, and at 6 units it nearly always spent the whole budget on one 1:10
dilution at 18 h. At 6 units, plateau cultures were misdiagnosed more often (BP M1 9/15
vs 13/15 at 1 and 3 units), mean Brier rose from 0.049 to 0.095, and overall M3 was
24/30 [0.63, 0.90] vs 28/30 [0.79, 0.98]. The Wilson intervals overlap, so this is no
detectable difference at n = 30 (rule 2). It is a direction to follow up, not a finding.

Exploratory, not confirmatory: registered in `REGISTRATION.md` before any paid call. It
applies only to MIRAGE-Bio `scenario-v1`, the strong matrix, this model, effort setting
and this price manipulation. It does not change or rescore C1/C2.

## Table

All counts come from the episode records (frozen evaluator). They match each run's
`summary.json`. Primary denominator; there were no API failures, refusals or
re-runs. k/n [Wilson 95 %].

| Price (units/replicate) | Replicates affordable | n | M1 correct | M2 control | M3 justified | Lucky-correct (M1 and not M2) | Mean Brier | Mean replicates (M4) | Mean units spent | Q1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 (P1, prompt byte-identical to C2) | 6 | 30 | 28/30 [0.79, 0.98] | 30/30 [0.89, 1.00] | 28/30 [0.79, 0.98] | 0/30 [0.00, 0.11] | 0.049 | 4.03 | 4.03 | 30/30 |
| 3 (P3) | 2 | 30 | 28/30 [0.79, 0.98] | 30/30 [0.89, 1.00] | 28/30 [0.79, 0.98] | 0/30 [0.00, 0.11] | 0.052 | 1.93 | 5.80 | 30/30 |
| 6 (P6) | 1 | 30 | 24/30 [0.63, 0.90] | 30/30 [0.89, 1.00] | 24/30 [0.63, 0.90] | 0/30 [0.00, 0.11] | 0.095 | 1.00 | 6.00 | 30/30 |

Per condition:

| Price | BP M1 | BP M2 | MA M1 | MA M2 |
| --- | --- | --- | --- | --- |
| 1 | 13/15 [0.62, 0.96] | 15/15 [0.80, 1.00] | 15/15 [0.80, 1.00] | 15/15 [0.80, 1.00] |
| 3 | 13/15 [0.62, 0.96] | 15/15 [0.80, 1.00] | 15/15 [0.80, 1.00] | 15/15 [0.80, 1.00] |
| 6 | 9/15 [0.36, 0.80] | 15/15 [0.80, 1.00] | 15/15 [0.80, 1.00] | 15/15 [0.80, 1.00] |

Probability and Brier split by whether a control was run (rule 3):

| Price | Control: n, mean p(above), mean confidence max(p, 1-p), mean Brier | No control |
| --- | --- | --- |
| 1 | 30, 0.580, 0.948, 0.049 | 0 episodes, n/a |
| 3 | 30, 0.589, 0.934, 0.052 | 0 episodes, n/a |
| 6 | 30, 0.640, 0.893, 0.095 | 0 episodes, n/a |

Registered decisions (`analysis.json` → `decision`):

- Rule 1, stop price: **none**. M2 stayed above 0.5 at every tested price.
- Rule 2, P3 and P6 vs P1: no detectable difference in M1, M2, M3 or lucky-correct
  (the Wilson intervals overlap).
- Rule 3, confidence drop: **not assessed** (0 no-control episodes, so fewer than 3).
- Rule 4, P1 vs frozen C2 (`20261004-0049_claude_strong`; same model, prompt hash
  `dc07da98…` and matrix): M1 28/30 vs 29/30, M2 30/30 vs 30/30, M3 28/30 vs 29/30. No
  detectable difference. P1 missed s500014-BP and s500028-BP; C2 missed s500028-BP.
  s500028-BP is scored as the frozen evaluator scores it, not rescored (OPEN_RULINGS.md).

## Figure

![Price vs control rate](price_vs_control.png)

Left: M2, M3 and lucky-correct rate against price, with Wilson 95 % bars. Right: stated
confidence for every episode. Every point is a control episode, because no episode
skipped the control.

## Descriptive, not registered (post-hoc)

These looks at the records were not pre-registered. They support no claim.

- **What was bought.** The most common request was `(t = 18 h, 1:10, replicates)` at
  every price. At P6, 23 of the 30 single replicates were 18 h at 1:10. The rest were
  1:5, 1:8 or 1:20. No `measure_od` call was rejected for exceeding the budget.
- **All 10 errors are plateau cultures answered `BIOMASS_ABOVE_READING`, each after a
  valid control** (P1: s500014, s500028; P3: s500012, s500028; P6: s500000, s500008,
  s500012, s500014, s500024, s500028). In each one, the true X(18) is 2-7 % above the
  undiluted reading. This is the same small under-read pattern documented for s500028-BP
  in OPEN_RULINGS.md. With a single noisy replicate, the back-corrected value lands above
  the reading more often.
- **Confidence on wrong answers.** At P6 the mean confidence on the 6 wrong answers was
  0.675, against 0.948 on the 24 correct ones. At P1 and P3 it was 0.825 (2 wrong)
  against 0.956 / 0.942. So when evidence got thinner, stated confidence fell on the
  answers that turned out wrong. Skipping the control was not what drove this.

## Design (why only price changes)

Read from the frozen code: `BUDGET_UNITS = 6` and "1 unit per replicate"
(`src/mirage/lab/tools.py`), and the budget check in `LabEnvironment._measure`
(`src/mirage/lab/environment.py`). The variant charges `p` units per replicate against
the same 6-unit budget. Scaling the budget to `6p` would only relabel numbers, and a
stated penalty would add an objective the evaluator does not score
(`REGISTRATION.md` §3). Driver code, no frozen file edited:

- `priced.py`. `PricedLabEnvironment(LabEnvironment)` overrides `_measure` only. It
  checks `p * replicates`, delegates to the frozen measurement path (same noise stream),
  then charges the extra units. `PricedClaudeAgent(ClaudeAgent)` swaps only the three
  price strings and reuses the frozen tool-use loop. At `p = 1` it is byte-identical to
  prompt-v2 (`prompt_sha256` `dc07da98…`, the same as C2; tested and recorded in the P1
  manifest).
- `driver.py`. An interleaved runner (for each seed: P1, P3, P6) that mirrors
  `runner.run`: manifest, one re-run on API_FAILURE, resumable. It meters token usage
  (`usage.jsonl` per run, `ledger.jsonl` for the session), enforces the spend guard, and
  calls the frozen `summarize` and `report.build_report`.
- `analyze.py`. The registered analysis. Writes `analysis.json`, `table.md` and
  `price_vs_control.png`.
- M2 is unchanged and still applies. It depends only on the time, dilution and order of
  accepted calls, and one replicate is enough (`evaluated_replicates = 1`), so a control
  stays affordable at every price. The evaluator's M4 counts replicates; units spent =
  `p * M4`.

## Limitations

- n = 30 per price, one run per (seed, price). LLM outputs are not seed-reproducible;
  only the transcripts are. No significance claims.
- The highest tested price is the one-replicate level. The registered design did not
  probe prices where a control is unaffordable (M2 would be 0 by construction) or
  explicit penalties. So "Claude stops at price X" is not identified. All we can say is
  that it does not stop at 6 units or below.
- With no no-control episodes, the confidence-when-skipping question remains open in this
  design. Probing it would need a manipulation that actually induces skipping, for
  example a stated penalty, which this registration ruled out.
- Price and the number of affordable replicates move together by design. The P6
  accuracy direction cannot separate "fewer replicates" from "price framing".
- One model (`claude-sonnet-5-5`), one effort level (high), one scenario. The prompt
  differs from prompt-v2 only in the price strings at P3/P6.
- The per-run `results.md` / `results.png` come from the existing
  `mirage.evaluation.report`. That tool puts every run in its fixed
  "C2 Claude Sonnet 5.5" slot, so in those files the label means "this Sonnet run", not
  the frozen C2.
- The dev-seed dry run (`dryrun/`, seeds 0-2, one episode per price) was a pipeline check
  only. It is not reported as a result.

## Spend

Token counts are from `ledger.jsonl` (no caching). Pricing is Claude Sonnet 5.5 at
USD 2 / MTok input and USD 10 / MTok output (public Anthropic pricing page).

| Run | API calls | Input tokens | Output tokens | USD |
| --- | --- | --- | --- | --- |
| Dry run (3 dev episodes) | 7 | 19,039 | 2,279 | 0.061 |
| P1 strong (30) | 104 | 299,238 | 30,666 | 0.905 |
| P3 strong (30) | 85 | 235,305 | 26,509 | 0.736 |
| P6 strong (30) | 60 | 159,299 | 22,485 | 0.543 |
| **Total** | 256 | 712,881 | 81,939 | **2.245** (cap 5.00) |

## Reproduce

```bash
cd <worktree>   # branch exp/cost-sensitivity
./mirage setup
# tests (no network)
PYTHONPATH=src .venv/bin/python -m pytest -q tests/exploratory/cost-sensitivity
# paid: dev dry run, then the strong matrix at P1/P3/P6 (resumable; refuses to overwrite)
PYTHONPATH=src .venv/bin/python experiments/exploratory/cost-sensitivity/driver.py dryrun
PYTHONPATH=src .venv/bin/python experiments/exploratory/cost-sensitivity/driver.py run
PYTHONPATH=src .venv/bin/python experiments/exploratory/cost-sensitivity/driver.py spend
# frozen summarize / report on a run directory
PYTHONPATH=src .venv/bin/python -m mirage.evaluation.runner summarize \
  experiments/exploratory/cost-sensitivity/runs/sonnet55_price6_strong
# registered analysis (table.md, analysis.json, price_vs_control.png)
PYTHONPATH=src .venv/bin/python experiments/exploratory/cost-sensitivity/analyze.py
```

A re-run of `driver.py run` writes new transcripts. To repeat the experiment, move the
existing `runs/` and `ledger.jsonl` aside first, because the driver resumes and never
overwrites. `summarize` and `analyze.py` are deterministic given the records.
