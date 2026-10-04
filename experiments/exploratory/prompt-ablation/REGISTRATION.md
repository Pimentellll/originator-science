# Pre-registration: prompt-ablation (exploratory)

Registered 2026-10-04, before any paid API call and before any result of this experiment was
computed. **Exploratory, not confirmatory.** Nothing here changes or rescores
`experiments/results/`, `results/`, `experiments/preregistration/`, `experiments/configs/` or
`docs/mirage-bio/`. Later changes go in a dated "Deviations" section at the end of this file.

## 1. Question and hypothesis

**Question.** Does Claude still run the dilution control when the system prompt never hints at
saturation, ceilings, or dilution as a remedy?

**H-abl (directional, exploratory).** Removing the dilution/ceiling cues from the system prompt
does not remove the control: under `prompt-v2-noceiling`, Claude Sonnet 5.5 (effort high) still
runs the frozen diagnostic control (M2) in most strong-matrix episodes, and its visible
reasoning still names a reader ceiling/saturation in most MA episodes.

**H-null-alt.** The cues in prompt-v2 drive the behaviour: without them, M2 falls clearly below
the frozen C2 rate (30/30).

## 2. Cue audit of prompt-v2 (`src/mirage/lab/tools.py`, `SYSTEM_PROMPT`)

prompt-v2 contains no literal "saturation", "ceiling", "linear range", "nonlinear" or
"dilute to fix". The phrases that can still cue the answer are:

| id | location | phrase | why it can cue | `noceiling` | `minimal` |
| --- | --- | --- | --- | --- | --- |
| S1 | system prompt, task sentence | "at the level the **undiluted** readings indicate" | implies a diluted reading could differ, i.e. dilution is the remedy | "undiluted" deleted | deleted |
| S2 | system prompt, task sentence | "higher than the **undiluted** readings indicate" | same | "undiluted" deleted | deleted |
| S3 | system prompt, task sentence | "or higher than the readings indicate" | raises the possibility that the reader under-reports | **kept**: it is the task question and the meaning of the frozen label `BIOMASS_ABOVE_READING` | kept |
| S4 | system prompt | "an aliquot of the culture was withdrawn and retained every hour" | advertises that saved samples can be re-measured | kept (resource description, not a ceiling cue) | deleted (the tool description says the same) |
| S5 | system prompt | "and to support your conclusion with evidence" | generic push to measure | kept (not ceiling-specific) | deleted |
| S6 | system prompt | "You are an autonomous scientist ...", "on a plate reader" | role/instrument framing; plate readers are known to saturate | kept | deleted |

Residual cues **outside** the system prompt. The task fixes tool definitions, the first user
message and the output format as identical to prompt-v2, so these stay in every arm, and the
ablation tests only the system prompt:

| id | location | phrase |
| --- | --- | --- |
| T1 | `measure_od` description | "diluted in sterile medium by the given factor (1 = undiluted; 10 = 1 part aliquot + 9 parts medium)" (the dilution affordance itself) |
| T2 | `measure_od` description | "Returns the blank-subtracted OD600 reading of each replicate exactly as read; no correction is applied." |
| T3 | `declare_state` / `submit_diagnosis` field descriptions | "higher than the undiluted readings indicate" (4 places) |
| T4 | `submit_diagnosis.late_biomass_estimate_od` | "the reading an undiluted sample would give **if the reader responded proportionally**" (strongest residual cue: it names a non-proportional reader) |
| T5 | first user message (`render_observation`) | "assay": "OD600 plate reader; blank-subtracted readings of undiluted culture" |
| T6 | output format | label name `BIOMASS_ABOVE_READING` |

## 3. Configurations

All arms: `claude-sonnet-5-5`, effort `high`, `MAX_TOKENS` 16000, 12 turns, budget 6 units,
the frozen `TOOL_DEFINITIONS`, first message, environment and evaluator, `tool_choice` auto
with parallel tool use disabled. That is the frozen C2 configuration except for the system
prompt. `prompt_sha256` is computed exactly as `mirage.lab.tools.prompt_sha256` does, with the
variant system prompt in place of `SYSTEM_PROMPT`.

| arm | prompt_version | status |
| --- | --- | --- |
| C2 (reference, frozen, not re-run) | `prompt-v2` | `experiments/results/20261004-0049_claude_strong` |
| A1 | `prompt-v2-noceiling` | run first |
| A2 | `prompt-v2-minimal` | run only if budget remains (§7) |

### 3.1 `prompt-v2-noceiling` (exact text)

```
You are an autonomous scientist working in a virtual microbiology laboratory.

A bacterial batch culture was inoculated at t = 0 h and incubated for 18 h. Its
optical density at 600 nm (OD600) was read every hour on a plate reader, and an
aliquot of the culture was withdrawn and retained every hour. The hourly readings
are provided in the first message.

Your task is to decide whether, over the final hours of the experiment, the
culture's biomass is at the level the readings indicate, or higher than
the readings indicate, and to support your conclusion with evidence.

You may request additional measurements with measure_od; each replicate reading
costs 1 unit from a budget of 6 units. Finish by calling submit_diagnosis. You have
at most 12 turns.
```

The only change from prompt-v2 is the deletion of the word "undiluted" in two places (S1, S2).

### 3.2 `prompt-v2-minimal` (exact text)

```
A bacterial batch culture was incubated for 18 h and its OD600 was read every hour. The
hourly readings are provided in the first message.

Decide whether, over the final hours of the experiment, the culture's biomass is at the
level the readings indicate, or higher than the readings indicate.

Tools: measure_od (each replicate reading costs 1 unit from a budget of 6 units),
declare_state (optional, free) and submit_diagnosis (ends the experiment). You have at
most 12 turns.
```

## 4. Seeds and matrix

- Scored: the frozen `strong` matrix of `experiments/configs/eval_matrix_v1.json`, seeds
  500000–500029 (15 BP, 15 MA), the same 30 episodes as C2. Each (seed, arm) is run once. An
  `API_FAILURE` episode is re-run once by the existing runner, and both attempts are kept.
- Dry run (pipeline check only, never reported as results): development seeds 0–3 (0, 2 BP;
  1, 3 MA), once per arm before that arm's strong run. Dry-run records stay in `.local/`; only
  their token usage enters the spend ledger.
- No model substitution. If `claude-sonnet-5-5` is unavailable, record that and stop.

## 5. Metrics

From the existing evaluator (`summarize`), primary population, overall and by condition:
M1 (correct), M2 (frozen diagnostic control run), M3 (correct AND justified by the control),
M4 (units used: mean, median, max), Q1 (descriptive), mean Brier, and status counts. Every
k/n has the evaluator's Wilson 95 % interval.

**Ceiling identification (C-id), secondary and descriptive.** An episode counts if its visible
agent text matches, case-insensitively, the regex

```
saturat|ceiling|linear(ity| range| regime| response)?|non-?linear|nonproportional|non-proportional|proportional|dynamic range|upper limit|detection limit|detector limit|compress|out of range|beer.?lambert|underestimat|under-?report|under-?read
```

Visible agent text is the `submit_diagnosis` rationale, all assistant `text` blocks and all
`declare_state` notes. Thinking blocks are excluded (they are returned empty). C-id is reported
as k/n with a Wilson 95 % interval, for C2 (computed read-only from its frozen transcripts) and
for each arm, overall and in MA. A match on "proportional" alone may echo T4, so C-id is also
reported without the terms `proportional|nonproportional|non-proportional`.
Then 2–3 short verbatim excerpts per arm are quoted.

## 6. Decision rule

Comparisons are against frozen C2 on the same 30 episodes, descriptive only (EXPERIMENT_PLAN
§10: no significance claims at n = 30).

- **Control effect:** an arm "reduced the control rate" only if the upper bound of its M2 Wilson
  95 % interval is below the lower bound of C2's M2 interval (0.886), i.e. M2 ≤ 23/30.
  Otherwise the result is reported as "no detectable difference in M2", not as equality.
- The same interval-overlap rule is applied to M3 and M1 against C2 (C2: 29/30, lower bound
  0.833).
- Brier, M4, Q1 and C-id are descriptive only.
- H-abl is supported for an arm if M2 shows no detectable reduction AND C-id (MA, without the
  "proportional" terms) is ≥ 8/15. It is contradicted if M2 shows a reduction. Any other
  outcome is reported as mixed.
- s500028-BP is not rescored (OPEN_RULINGS §H). A miss there is reported as it is scored.

## 7. Spend cap and pricing

- Cap: **$5.00** of Anthropic API usage for this whole session, dry runs included.
- Prices (Anthropic public pricing page, read 2026-10-04): Claude Sonnet 5.5 $2 / MTok input,
  $10 / MTok output, $2.50 / MTok 5-minute cache write, $4 / MTok 1-hour cache write,
  $0.20 / MTok cache read.
- Projection from frozen C2 usage (about 303k input and 30k output tokens over 30 episodes):
  about $0.91 per strong-matrix arm and about $0.12 per 4-episode dry run, so both arms come to
  about $2.1.
- Enforcement: every API call's usage is appended to a committed spend ledger. Before each
  call the driver refuses to proceed if logged spend plus a worst-case next call (current
  input estimate plus 16000 output tokens) would exceed $5.00. If the cap stops an arm
  mid-run, that arm is reported as partial with its actual n.
- Order: A1 dry run, then A1 strong. A2 dry run and A2 strong run only if logged spend plus
  1.5 × A1's measured cost (dry run + strong) is ≤ $5.00.

## 8. Allowed claims

Only "In MIRAGE-Bio scenario-v1, on these 30 strong-matrix episodes, Claude Sonnet 5.5
(effort high) with prompt X achieved k/n [Wilson 95 % CI] ..., compared with k/n for the
frozen C2 run with prompt-v2." No claims beyond this scenario, model, configuration and
sample, and no comparison with models not run on this matrix.

## Deviations

### 2026-10-04: blocked before any run

`ANTHROPIC_API_KEY` was not set in this session and no secret was available. No API call was
made, and no dry-run or strong-matrix episode exists. The only computed output is the
read-only C2 baseline from `analyze.py` (C-id on frozen transcripts), produced after this
registration was pushed. The registered design is unchanged and can be executed as written.
