# Result: does a non-Claude model run the dilution control?

**Exploratory, not confirmatory.** These results do not change, re-score or extend the frozen
results in `experiments/results/`. Registration: [`REGISTRATION.md`](REGISTRATION.md) (commit
29ce4be, pushed before any scored call). Runs:
`runs/20261004-1202_openai_responses_strong_Y1/` (Y1) and `runs/20261004-1308_kimi_chat_strong_Y2/` (Y2).

**Headline.** On the 30-episode strong matrix (seeds 500000–500029), GPT-6 Luna (`gpt-6-luna`,
reasoning effort `high`, OpenAI Responses API) ran the diagnostic dilution control in **30/30**
episodes (M2 [0.89, 1.00]). It reached M3 = **24/30** justified [0.63, 0.90], against 29/30 for
both frozen Claude runs. Under the registered rule (§5), the control is **retained**, and M3 is
**"lower, worth following up"** (the intervals overlap). That is not a detectable drop. All six misses are
BIOLOGICAL_PLATEAU cultures where Luna diluted correctly but called the few-percent dilution
excess (2.3–4.0 %) a measurement artifact. That is the same failure as `s500028-BP` (OPEN_RULINGS §H),
which Luna also missed. Unlike Claude, Luna was confident when wrong (p_above 0.80–0.99), so its
mean Brier is 0.178 against Claude's 0.028–0.030. The full run cost **$0.0244**.

**Y2, Kimi K3** (`k3`, reasoning effort `high`, through Kimi Code's chat-completions endpoint; see
the second Deviations entry) also ran the control in **30/30** episodes and reached M3 = **27/30**
[0.74, 0.97]. That is again "lower, worth following up" under §5, with overlapping intervals. Its
three misses are BIOLOGICAL_PLATEAU cultures where it diluted correctly and called the excess an
artifact, at p_above 0.78–0.80, which is less confident than Luna. It got `s500028-BP` right
(p_above 0.30), which both Claude models and Luna missed. Mean Brier is 0.069. Y2 ran after Y1's result was known, so it
is not blind to it.

## Table

Primary analysis (DIAGNOSED + NO_DIAGNOSIS), n = 30, k/n with the evaluator's Wilson 95 %
intervals. C1 and C2 are the frozen references and were not re-run. Tokens and USD come from
`usage.jsonl` at the registered prices (§6).

| Config | Model | M1 correct | M2 control | M3 justified | M4 units mean | Q1 | Brier | calls/ep | USD run |
|---|---|---|---|---|---|---|---|---|---|
| C1 (frozen) | claude-opus-5-5, high | 29/30 [0.83, 0.99] | 30/30 [0.89, 1.00] | 29/30 [0.83, 0.99] | 5.80 | 30/30 | 0.028 | 4.53 | 2.513 |
| C2 (frozen) | claude-sonnet-5-5, high | 29/30 [0.83, 0.99] | 30/30 [0.89, 1.00] | 29/30 [0.83, 0.99] | 3.97 | 30/30 | 0.030 | 3.50 | 0.910 |
| **Y1** | gpt-6-luna, high | 24/30 [0.63, 0.90] | 30/30 [0.89, 1.00] | 24/30 [0.63, 0.90] | 6.00 | 30/30 | 0.178 | 3.47 | 0.024 |
| **Y2** | k3 (Kimi Code), high | 27/30 [0.74, 0.97] | 30/30 [0.89, 1.00] | 27/30 [0.74, 0.97] | 6.00 | 30/30 | 0.069 | 2.90 | 1.660\* |

\* List-price equivalent at the Kimi K3 platform price. Kimi Code calls use the user's
membership credits, so this is not an actual charge.

By condition, Y1 M3 is 15/15 for MEASUREMENT_ARTIFACT (Brier 0.0001) and 9/15 for
BIOLOGICAL_PLATEAU (Brier 0.356). Y2 M3 is 15/15 for MEASUREMENT_ARTIFACT (Brier 0.0003)
and 12/15 for BIOLOGICAL_PLATEAU (Brier 0.138).

Status: 30/30 DIAGNOSED. There were no API_FAILURE, REFUSED or NO_DIAGNOSIS episodes, so there
were no re-runs (`manifest.json` `reruns: {}`). Intention-to-treat equals primary. Every response reported
`model = gpt-6-luna`.

Tokens: 195,922 input (130,896 cached) and 33,252 output over 104 calls. The two-episode
development dry run cost $0.0015, so the experiment total is $0.0260 against the $2.00 cap.

Y2: 30/30 DIAGNOSED, no re-runs (`reruns: {}`), and every response reported `model = k3`.
Tokens: 253,537 input (157,696 cached) and 88,345 output over 87 calls. The first 16 episodes
ran one at a time. For speed, the remaining 14 were then run by five worker processes
(`parallel_resume.py`, same per-episode logic as `runner.run`), and a final `--resume` wrote the
summary. The episode in progress at the switch (`s500016-BP`) was abandoned unfinished, before
any diagnosis, and run again from scratch. Its calls are included in the 87 calls and the cost.
List-price equivalent: $1.660 for the run plus $0.132 for the two-episode dry run, $1.792 in total,
within the registered $2.00 per-provider cap.

## Failure analysis

| Class | justified | correct w/o control | wrong after control | wrong w/o control | NO_DIAG | API_FAIL | REFUSED |
|---|---|---|---|---|---|---|---|
| Y1 | 24 | 0 | 6 | 0 | 0 | 0 | 0 |
| Y2 | 27 | 0 | 3 | 0 | 0 | 0 | 0 |

Every BP culture, sorted by plateau gap. The gap is true plateau biomass over the noise-free
undiluted reading, minus 1, computed from each episode's `k_odeq`, `s_odeq` and `n`.

| Episode | gap | C1 | C2 | Y1 | Y1 p_above | Y2 | Y2 p_above |
|---|---|---|---|---|---|---|---|
| s500028-BP | 4.0 % | miss | miss | miss | 0.99 | ok | 0.30 |
| s500000-BP | 4.0 % | ok | ok | ok | 0.03 | miss | 0.78 |
| s500002-BP | 3.6 % | ok | ok | ok | 0.08 | ok | 0.03 |
| s500006-BP | 3.5 % | ok | ok | ok | 0.05 | ok | 0.10 |
| s500024-BP | 3.3 % | ok | ok | miss | 0.90 | ok | 0.15 |
| s500008-BP | 3.3 % | ok | ok | miss | 0.98 | miss | 0.80 |
| s500014-BP | 3.1 % | ok | ok | miss | 0.99 | ok | 0.10 |
| s500020-BP | 3.1 % | ok | ok | ok | 0.12 | miss | 0.78 |
| s500026-BP | 2.9 % | ok | ok | miss | 0.94 | ok | 0.05 |
| s500022-BP | 2.6 % | ok | ok | ok | 0.02 | ok | 0.05 |
| s500012-BP | 2.6 % | ok | ok | ok | 0.25 | ok | 0.18 |
| s500018-BP | 2.5 % | ok | ok | ok | 0.03 | ok | 0.03 |
| s500010-BP | 2.4 % | ok | ok | ok | 0.04 | ok | 0.12 |
| s500004-BP | 2.3 % | ok | ok | ok | 0.02 | ok | 0.10 |
| s500016-BP | 2.3 % | ok | ok | miss | 0.80 | ok | 0.12 |

- **The misses do not track the gap.** Luna was right on three cultures with gaps of 3.5–4.0 % and
  wrong on one at 2.3 %. Its call seems to depend on the noise in its dilution reads rather than on a
  consistent threshold.
- **Example, s500008-BP:** "Diluting the retained 18 h aliquot gave mean readings of 0.2639 at
  5-fold dilution and 0.1312 at 10-fold dilution … indicates the undiluted reading
  underestimates late biomass by about 0.10 OD (roughly 9%)". Answered `BIOMASS_ABOVE_READING`,
  p 0.98. The arithmetic is right. What it gets wrong is interpreting a small dilution excess as an
  artifact, the ambiguity documented in OPEN_RULINGS §H.

- **Y2's misses do not track the gap either.** Kimi missed cultures at 4.0, 3.3 and 3.1 % and got
  the 4.0 % `s500028-BP` right. Its three misses are the cultures where it put p_above at 0.78–0.80.
  On every other BP culture it put p_above at 0.30 or below.

## Limitations

- n = 30 with one seed set: no significance claims, and "lower" is not a measured ranking.
- The prompt (`prompt-v2`, sha256 `dc07da98…`, identical to C2) was written against Claude, so the
  gap may reflect the prompt rather than the model.
- The tools were converted to Responses API function tools (`strict: true`, sha256 `3447043c…`).
  Semantics are unchanged, but the wire format differs from the Anthropic runs.
- One model, one effort level and one provider. There is no claim about model families in general.
- The scored question has no "how much counts" threshold for plateau residuals (OPEN_RULINGS
  §H). All six misses fall into that ambiguity, and none is re-scored.
- Y2 used Kimi Code's endpoint and model id (`k3`), not the standard Moonshot API named in the
  registration, because the supplied key works only there. Y2 was run after Y1's result was known.
