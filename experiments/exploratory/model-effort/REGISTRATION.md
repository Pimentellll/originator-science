# Pre-registration: model size and reasoning effort (exploratory)

Registered 2026-10-04 (UTC), before any paid API call and before any result of this experiment
was computed. The only API call made so far is the free `GET /v1/models` listing, saved as
[`models_list.json`](models_list.json). **Exploratory, not confirmatory**: nothing here changes,
re-scores or extends the frozen results in `experiments/results/`.

## 1. Question and hypothesis

**Question.** Is justified diagnosis (M3) in MIRAGE-Bio `scenario-v1` robust to a smaller model and
to lower reasoning effort?

- **H-size.** The smallest available current Claude model, under the C1/C2 adapter and prompt-v2,
  still runs the frozen diagnostic control and reaches M3 comparable to C2 (Sonnet 5.5, high:
  29/30). *Alternative:* M3 drops, through skipped controls (M2 < 30/30) or wrong answers after a
  control.
- **H-effort.** Lowering effort from `high` to `low` leaves M3 unchanged for Sonnet 5.5 (vs C2) and
  for Opus 5.5 (vs C1), while cutting output tokens per episode. *Alternative:* lower effort
  skips or under-uses the control, or misreads its result.

## 2. Model availability (recorded 2026-10-04)

`client.models.list()` (anthropic SDK 1.10.0) returned 13 ids, saved verbatim in
`models_list.json`: claude-sonnet-5-5, claude-opus-5-5, claude-fable-5-1, claude-opus-5,
claude-sonnet-5, claude-fable-5, claude-opus-4-8, claude-opus-4-7, claude-sonnet-4-6,
claude-opus-4-6, claude-opus-4-5-20251101, claude-haiku-4-5-20251001, claude-sonnet-4-5-20250929.

The public model pages (platform.claude.com, Opus 5.5 and Sonnet 5.5 overviews, read 2026-10-04)
list the current lineup as Fable 5.1, Opus 5.5, Sonnet 5.5 and Haiku 4.5. No Haiku 5.x id is
available. **The smallest available current model is therefore `claude-haiku-4-5-20251001`**
(cheapest, "Fastest" latency tier). The same pages say Haiku 4.5 has *extended* (manual) thinking
and **no effort parameter** ("Default effort: not supported"). Opus 5.5 has adaptive thinking that
is always on, with API default effort `medium`. Sonnet 5.5 has adaptive thinking, default `high`.

## 3. Configurations

Every configuration uses the unmodified `ClaudeAgent` request (prompt-v2, `prompt_sha256`
`dc07da98…d91d1`, `TOOL_DEFINITIONS`, `tool_choice` auto with no parallel tool use,
`max_tokens` 16000, at most 12 turns, budget 6, no model fallback). Only the model and
`output_config.effort` change. A driver subclass sets them; no frozen source is edited.

| ID | Model | Effort | Compared with | Priority |
|---|---|---|---|---|
| **X1** | `claude-haiku-4-5-20251001` | `high` (see contingency) | C2 (Sonnet 5.5, high), C1 | (a) |
| **X2** | `claude-sonnet-5-5` | `low` | C2 (same model, high) | (b) |
| **X3** | `claude-opus-5-5` | `low` | C1 (same model, high) | (c), only if budget allows (§6) |

**X1 contingency, decided now.** X1 first sends exactly the C1 request with
`output_config.effort = "high"`. If the API rejects that request because Haiku 4.5 has no effort
parameter (an HTTP 400 that names `effort` or `output_config`, seen in the dry run), X1 instead
**omits `output_config`** and records `effort = null` in the manifest. The docs say `high` is the
API default, identical to omitting the parameter, so this is the closest available setting. X1
does **not** turn on extended thinking: the adapter never sets `thinking`, and adding it would
change a second variable. If Haiku 4.5 fails for any other reason (not found, permission), X1 is
recorded as unavailable and not replaced by another model.

**Fixed references (not re-run, read only):** C1 `experiments/results/20261003-2323_claude_strong`
(Opus 5.5, high) and C2 `experiments/results/20261004-0049_claude_strong` (Sonnet 5.5, high).

## 4. Seeds and procedure

1. **Dry run (pipeline check only, never reported as results):** X1 and X2, each on development
   seeds 0 (BP) and 1 (MA), from a driver-local `dev_matrix.json`. Results go to
   `.local/runs/model-effort/`, which is not committed. The dry run checks that requests succeed,
   that usage is logged and that the cost estimate is sane. A driver bug found here is fixed
   before any strong-matrix episode. The prompt, tools and scoring never change.
2. **Scored runs:** X1, then X2, then X3 (if §6 allows), each on the **strong matrix** (seeds
   500,000–500,029, 15 BP and 15 MA, `experiments/configs/eval_matrix_v1.json`,
   `matrix_sha256` `5d10b4d2…134c`), through `mirage.evaluation.runner.run`. X3 gets its own
   2-episode dry run (seeds 0, 1) just before its strong run.
3. Each (seed, configuration) is run **once**. An `API_FAILURE` episode is re-run once by the
   existing runner logic, and both attempts are kept (`reruns/`).
4. Run records go to `experiments/exploratory/model-effort/runs/<run_id>/` (manifest, episodes,
   reruns, usage.jsonl, summary.json from the existing `summarize`, results.md).

## 5. Metrics and decision rule

Per configuration, from the existing evaluator (`summary.json`, primary analysis):
M1, M2, M3 as k/30 with the evaluator's Wilson 95 % intervals, M4 (mean, median, max units),
Q1 (k/30), mean Brier (O1). Per BP/MA block as well. From `usage.jsonl`: input and output tokens per
episode, API calls per episode, and USD per episode at the public prices in §6.

**Failure analysis (audit breakdown).** Every episode is put in exactly one class:
justified (correct + control); correct without control; wrong after a control; wrong without a
control; NO_DIAGNOSIS; API_FAILURE; REFUSED. For every non-justified episode, the failed M2 and Q1
clauses of each measurement (`metrics.failed_clauses`) are listed. **s500028-BP** is reported for
each configuration: answer, probability, and whether it repeats the C1/C2 miss. It is not
re-scored (OPEN_RULINGS §H). A "new failure type" is any class or failed clause not seen in C1 or
C2.

**Decision rule (descriptive; no significance claims at n = 30, EXPERIMENT_PLAN §10).** For each
configuration, compared with its reference (X1 vs C2, X2 vs C2, X3 vs C1) on overall M3:

- **"Detectable drop"** if the configuration's Wilson 95 % upper bound is below the reference's
  Wilson 95 % lower bound (0.833 for 29/30, i.e. M3 ≤ 20/30).
- **"Lower, worth following up"** if the intervals overlap but M3 is at least 3 episodes below the
  reference (M3 ≤ 26/30).
- Otherwise **"no detectable difference at n = 30"**. This is not a claim of equality.

M3 is called "robust" to a factor only for configurations in the last class. Token and cost
differences are reported descriptively (means per episode), with no test.

## 6. Spend cap and pricing

- **Cap: $5.00** of Anthropic API usage for the whole session, dry runs included.
- Prices (public Anthropic pricing and model pages, read 2026-10-04), USD per million tokens,
  input / output (5-minute cache write, 1-hour cache write, cache read):
  Haiku 4.5 1 / 5 (1.25, 2, 0.10); Sonnet 5.5 2 / 10 (2.50, 4, 0.20);
  Opus 5.5 4 / 20 (5, 8, 0.20). The adapter sets no cache control, so caching is expected to be
  zero.
- Cost is computed from the `usage` of every response and appended to a session-wide
  `spend_ledger.jsonl`. **Before every call** the driver adds a worst-case estimate for that call
  (previous input + 2,000 input tokens, plus 16,000 output tokens) to the ledger total and stops
  if the sum would exceed $5.00. A run stopped this way is reported as incomplete, with its k/n
  over the episodes completed, never as a 30-episode result.
- Expected cost from the frozen token counts: C2 (Sonnet high) cost $0.91 for 30 episodes and C1
  (Opus high) $2.51. Low effort is expected to cost no more than high.
- **X3 rule:** X3 (dry run and strong run) starts only if, after X1 and X2, at least **$2.90**
  remains (C1's $2.51 plus 15 %). Otherwise X3 is recorded as not run for budget.

## 7. Claims allowed

Only descriptive claims about these configurations, this scenario and these 30 episodes, compared
only with C1 and C2 (same matrix). No claims about real biology, about other models, or about
"robustness" beyond the rule in §5. Haiku 4.5 differs from the 5.5 models in generation,
tokenizer and thinking mode, not only in size. Any X1 difference is a difference of that model,
not of "size" alone.

## Deviations

None at registration time. Dated entries below were added after the registration commit (0437e0f).

- **2026-10-04, X1 contingency triggered (pre-registered, not a protocol change).** The X1 dev dry
  run with `output_config: {"effort": "high"}` failed on both seeds with HTTP 400 "This model does
  not support the effort parameter." (API_FAILURE; both attempts kept in the uncommitted dev run
  `20261004-1058_claude_dev_X1`; no tokens billed). As registered in §3, X1 therefore omits
  `output_config` (`--no-effort`, manifest `effort = null`). The X1 dev re-run and all X1 strong
  episodes use this setting.
- **2026-10-04, driver fixes before any strong episode.** (1) The run id gets a `-noeffort` suffix when
  `output_config` is omitted, so the X1 re-run does not collide with the failed run directory in the
  same minute. (2) If a response reports a model id that is not in the price table, the cost is priced
  at the requested model. Neither fix changes prompts, tools, scoring or the strong-matrix procedure.
 Later deviations are added here with a date; the text above is not edited.
