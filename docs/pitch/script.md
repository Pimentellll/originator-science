# MIRAGE-Bio pitch script (about 3 minutes)

Every number below comes from a committed file; see the table in "Sources" at the end. The demo
episode is an illustration. The results table is the claim (EXPERIMENT_PLAN §10).

## 1. The question (0:00–0:30)

> The benchmark does not ask whether the AI knows the answer. It puts the AI in a situation where
> the answer cannot be known from the evidence it has, and asks whether it knows which experiment
> would make it knowable.

MIRAGE-Bio is a small virtual microbiology lab. The agent watches a culture's OD600 readings
level off. That flat line has two hidden explanations. Either the culture really stopped growing,
or the plate reader saturated while the biomass went higher. The passive readings cannot tell
these apart. One diluted measurement of a late sample can.

**Show:** `latent_reveal.png`.

## 2. Why it is a fair test (0:30–1:10)

The ambiguity is measured, not asserted. Using passive readings only, the analytic Bayes ceiling
is 0.576. That is the best any classifier can do with full knowledge of the simulator. Our
PassiveBayes classifier reaches 0.567. In this demo pair, both cultures show the same curve at
about 1.0, while their true biomass is 1.03 and 4.00.

Gate 0 checks this before any agent runs, and it is frozen in `experiments/results/gate0/`.
Scoring is deterministic and uses no LLM judge. An answer counts as justified only when it rests
on evidence the agent chose to collect itself.

**Show:** `passive_overlap.png`.

## 3. Demo (1:10–2:00)

Replay a recorded Claude episode, fully offline:

```bash
python -m mirage.demo.replay \
  experiments/results/20261003-2323_claude_strong/episodes/s500001-MA.json --pace 0.5
```

The passive readings flatten at about 0.76. Claude dilutes the 18 h sample 1:10 and 1:20 and
corrects back to 2.64 and 2.57. It answers `BIOMASS_ABOVE_READING`. The reveal shows a true
biomass of 2.55.

**Show:** `demo_s500001-MA.png`.

## 4. Results (2:00–2:40)

Claude Opus 5.5 (effort high, prompt-v2) ran 30 evaluation episodes, 15 of each condition:

- Justified accuracy M3 was 29/30 [Wilson 95% 0.83–0.99]. It ran a diagnostic control in 30/30
  episodes and used 5.80 of its 6 budget units on average.
- The scripted GoodScientist got 30/30 using 3 units. PassiveBayes got 20/30 correct and 0/30
  justified, as it should, because it never collects evidence.
- The single miss was a plateau culture. The reader under-reads there by about 4%, and Claude's
  dilutions overshot. We report it rather than re-score it (OPEN_RULINGS §H).

**Show:** `results.png`.

## 5. Close (2:40–3:00)

Every number here can be recomputed from the committed configuration and records. The
contribution is the evaluation construction: paired ambiguous worlds, hidden ground truth,
active evidence collection, and scoring that requires evidence. It covers one scenario, one model
and n = 30. It says nothing about real bacteria, real plate readers, or AI scientists in general.

## Sources

| Number | File |
|---|---|
| ceiling 0.576; PassiveBayes 0.567 | `experiments/results/gate0/summary.json` (`checks.G0-A`) |
| 1.03 vs 4.00 demo pair | `experiments/results/gate0/latent_reveal.png` |
| 0.76, 2.64, 2.57, 2.55 | `experiments/results/20261003-2323_claude_strong/replay/s500001-MA.txt` |
| M2/M3/M4 for all three agents, Wilson intervals | `experiments/results/20261003-2323_claude_strong/results.md` |
| s500028-BP miss, about 4% gap | `experiments/results/20261003-2323_claude_strong/INTERPRETATION.md` |

## Do not say (ANALYSIS §18, EXPERIMENT_PLAN §10, DIFFERENTIATION §7)

- "first", "Claude can do science", or anything about real organisms or instruments.
- "statistically significant", or any comparison with models we did not run.
- That PassiveBayes is optimal, or that the LLM runs are reproducible from seeds. Only the
  saved transcripts are.
