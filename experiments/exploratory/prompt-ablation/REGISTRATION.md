# Exploratory registration: prompt cue ablation (prompt-v2-noceiling, prompt-v2-minimal)

| Field | Value |
|---|---|
| Status | **Exploratory, not confirmatory.** Registered before any paid API call and before any result of this experiment was computed. |
| Branch | `exp/prompt-ablation` off `main` at `d56cb1a` |
| Registered | 2026-10-04 (this commit is the first commit on the branch) |
| Scope | MIRAGE-Bio v0.1 `scenario-v1`, strong matrix only. No change to frozen source, configs, results or prompt-v2. |

## 1. Question

Does Claude Sonnet 5.5 (effort high, the C2 configuration) still run the dilution control
when the prompt never hints at saturation, a ceiling, a linear range or dilution as a remedy?

## 2. Cue inventory (everything the model sees under prompt-v2)

prompt-v2 (`src/mirage/lab/tools.py`, `prompt_sha256` `dc07da98…91d1`) contains **no** explicit
mention of saturation, ceiling, linear range or non-linearity. The phrases below are every phrase
that could still cue the answer. "Kind" is my classification.

| ID | Where | Phrase | Kind |
|---|---|---|---|
| S1 | system prompt | "read every hour on a plate reader" | instrument named (weak domain cue: plate readers have a finite linear range) |
| S2 | system prompt | "an aliquot of the culture was withdrawn and retained every hour" | affordance (re-measurement possible) |
| S3 | system prompt | "at the level the **undiluted** readings indicate" | dilution cue (implies diluted readings exist and may differ) |
| S4 | system prompt | "or higher than the **undiluted** readings indicate" | dilution cue + task-intrinsic hypothesis (readings may under-report) |
| S5 | system prompt | "and to support your conclusion with evidence" | invites experimentation (not ceiling-specific) |
| S6 | system prompt | "You may request additional measurements with measure_od" | affordance |
| T1 | `measure_od.description` | "diluted in sterile medium by the given factor (1 = undiluted; 10 = 1 part aliquot + 9 parts medium)" | dilution affordance |
| T2 | `measure_od.description` | "Returns the blank-subtracted OD600 reading … exactly as read; no correction is applied." | hints that readings need correcting |
| T3 | `measure_od.dilution_factor` | "from 1 (undiluted) to 100" | dilution affordance |
| T4 | `declare_state.description`, `declare_state.p_biomass_above_reading`, `submit_diagnosis.diagnosis`, `submit_diagnosis.p_biomass_above_reading` | "higher than the **undiluted** readings indicate" / "the level the **undiluted** readings indicate" | dilution cue (4 occurrences) |
| T5 | `submit_diagnosis.late_biomass_estimate_od` | "expressed as the reading an undiluted sample would give **if the reader responded proportionally**" | **strongest cue**: implies the reader may not respond proportionally (= non-linearity / saturation) |
| T6 | `submit_diagnosis.rationale` | "Evidence-based justification." | invites experimentation |
| O1 | first user message, `experiment.assay` | "OD600 plate reader; blank-subtracted readings of **undiluted** culture" | dilution cue + instrument |
| O2 | first user message, `limits.dilution_factor` | "1 to 100" | dilution affordance |
| L1 | label / enum names | `BIOMASS_AS_READ`, `BIOMASS_ABOVE_READING`, `p_biomass_above_reading` | task-intrinsic; part of the output format, **not removable** |

The reminder text ("Continue. Use the tools, and finish by calling submit_diagnosis.") has no cue.

## 3. Configurations

All: `claude-sonnet-5-5`, effort `high`, adaptive thinking (model default), `MAX_TOKENS` 16000,
≤ 12 turns, budget 6, `tool_choice` auto with parallel tool use disabled, no model fallback.
The agent is the frozen `mirage.agents.claude.ClaudeAgent`, subclassed in driver code under this
directory; only the system prompt, the tool descriptions and (for minimal) the observation's
`experiment.assay` string are swapped. Tool names, `input_schema` structure, parameter names, types,
enums, `required`, `strict` and `additionalProperties` are identical in every variant, so the output
format and the evaluator are unchanged.

| ID | prompt_version | Changes vs prompt-v2 |
|---|---|---|
| C2 (frozen reference, not re-run) | `prompt-v2` | none; `experiments/results/20261004-0049_claude_strong/` |
| X1 | `prompt-v2-noceiling` | **System prompt only**: S3 and S4 lose the word "undiluted" ("at the level the readings indicate, or higher than the readings indicate"). Tool definitions and observation byte-identical to prompt-v2 (as the experiment brief requires), so cues T1–T6, O1, O2, L1 remain. S1, S2, S5, S6 are kept: they do not mention saturation, ceilings or dilution. |
| X2 | `prompt-v2-minimal` | System prompt reduced to the task statement and a tool list. Tool descriptions neutralised: T2 → "Returns the OD600 reading of the diluted sample for each replicate."; T3 → "from 1 to 100"; T4 "undiluted" removed; T5 → "Your estimate of the culture's OD600 at 18 h; null if you have no estimate."; T6 → "Justification for the diagnosis."; T1 → "after diluting it in medium by the given factor". Observation O1 → "OD600; blank-subtracted readings of culture". Remaining (unavoidable) cues: the `dilution_factor` parameter (T1/T3/O2 affordance) and the label names (L1). |

Exact X1 system prompt:

```text
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

Exact X2 system prompt:

```text
You are working in a virtual microbiology laboratory.

A bacterial batch culture was incubated for 18 h and its OD600 was read every hour.
The readings are in the first message.

Task: decide whether, over the final hours, the culture's biomass is at the level
the readings indicate (BIOMASS_AS_READ) or higher (BIOMASS_ABOVE_READING).

Tools: measure_od (1 budget unit per replicate; 6 units in total), declare_state
(optional, free), submit_diagnosis (ends the experiment). At most 12 turns.
```

Exact X2 tool descriptions are in `variants.py` committed with the driver; they follow the
substitutions in the table above and nothing else. If any wording in `variants.py` differs from
this table, that is reported as a deviation.

## 4. Seeds, matrix and run order

1. **Dry run (pipeline check, never reported as a result):** development seeds 0 and 1 for X1,
   then 0 and 1 for X2 (4 episodes; seed 0 BP, seed 1 MA by the parity rule).
2. **X1 on the strong matrix**: seeds 500000–500029, 15 BP + 15 MA, from
   `experiments/configs/eval_matrix_v1.json` (`strong`), exactly once per seed.
3. **X2 on the strong matrix**, only if the spend rule (§7) allows the whole run.

An `API_FAILURE` episode is re-run once with the same seed; both records are kept (same
mechanism as the frozen runner). A dry-run bug is fixed in the driver before step 2 and noted as a
deviation; prompts are not changed after the dry run.

## 5. Metrics

From the frozen evaluator (`mirage.evaluation.metrics.aggregate` via `runner.summarize`), primary
denominator, overall and per condition: M1, M2, M3 (k/n with Wilson 95 %), M4 (mean, median, max),
Q1, O1 (mean Brier), status counts; ITT if any API_FAILURE/REFUSED.

Secondary, descriptive, computed by driver code from the committed records (not an evaluator
metric, no LLM judge):

- **Ceiling named (visible text).** An episode counts if the visible assistant text (text blocks,
  `declare_state.notes`, `submit_diagnosis.rationale`; thinking is redacted by the API and is not
  available) matches, case-insensitively, the regex
  `saturat|ceiling|linear range|linearity|non-?linear|proportional|compress|dynamic range|upper limit|detection limit|beer.?lambert|under-?(?:read|report|estimat)`.
  Reported as k/n for X1, X2 and (read-only analysis of the frozen records) C2.
- **Ceiling named before any evidence.** Same regex, restricted to text emitted in turns before
  the first `measure_od` result. (Expected to be rare because thinking is redacted.)
- **First measurement diagnostic.** The first `measure_od` call has `time_h` in [12, 18] and
  `dilution_factor` ≥ 1.1 (the frozen D_diag).
- **Excerpts.** 2–3 short quotations: the `submit_diagnosis.rationale` of the first BP and the first
  MA episode (seed order) of each variant run, plus the first episode with M2 = 0 if any.

## 6. Decision rule

No significance tests (EXPERIMENT_PLAN §8, §10).

- **Control behaviour retained** for a variant if its M2 Wilson 95 % lower bound > 0.65 (the H2
  threshold); **lost** if the upper bound < 0.65; otherwise **inconclusive**.
- **Detectable difference from C2** on M1, M2 or M3 only if the variant's Wilson 95 % interval and
  C2's do not overlap. Overlapping intervals are reported as "no detectable difference at n = 30",
  never as equality.
- M4, Q1 and Brier differences are reported descriptively only.
- s500028-BP is scored as the evaluator scores it; it is not rescored (OPEN_RULINGS §H).

## 7. Spend cap

- Hard cap **$5.00**; the driver stops at **$4.50** estimated cumulative spend for this session.
- Cost is estimated from every API response's `usage` (logged per call to `usage.jsonl` in each run
  directory) at current public pricing for Claude Sonnet 5.5: **$2 / MTok input, $10 / MTok output**
  (cache read $0.20, cache write $2.50 per MTok; no caching is used).
- Before each episode the driver checks that cumulative spend + $0.15 (a per-episode allowance well
  above the C2 mean of ≈ $0.03) ≤ $4.50; otherwise it stops and the run is reported as partial.
- Expected: C2 used ≈ 303k input + 30k output tokens per 30 episodes ≈ $0.91; dry run ≈ $0.15;
  X1 + X2 ≈ $2.

## 8. Claims

EXPERIMENT_PLAN §10 applies: results are about Sonnet 5.5, effort high, these prompts, this
scenario and these 30 episodes. No comparison with models not run on this matrix. Exploratory
results do not replace or re-score any frozen result.

## Deviations

None yet. Later deviations are appended here with a date; this registration is not edited
silently.
