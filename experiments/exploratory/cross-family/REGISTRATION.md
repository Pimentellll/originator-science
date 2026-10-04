# Pre-registration: does the control generalise beyond Claude? (exploratory)

Registered 2026-10-04 (UTC), before any scored API call and before any result of this
experiment was computed. The only calls made so far are the free `GET /v1/models` listing (saved
as [`openai_models_list.json`](openai_models_list.json)) and one 63-token tool-call probe, to
check that `gpt-6-luna` accepts function tools through the Responses API. The probe used none of
the MIRAGE prompt or tools. **Exploratory, not confirmatory**: nothing here changes, re-scores or
extends the frozen results in `experiments/results/`.

## 1. Question and hypothesis

**Question.** Is running the diagnostic control (M2), and the justified diagnosis it allows (M3),
a property of Claude? Or does a model from a different family, given the same prompt, tools and
scorer, also run the dilution control?

- **H-family.** A non-Anthropic model given the unmodified prompt-v2 task runs the frozen
  diagnostic control in most episodes (M2 Wilson 95 % lower bound > 0.65), as C1 and C2 did.
- *Alternative.* It answers from the passive readings (as PassiveBayes does, M2 0/30), or reaches
  answers that are right but unjustified.

## 2. Configurations

| ID | Provider / API | Model | Reasoning | Compared with |
|---|---|---|---|---|
| **Y1** | OpenAI Responses API (`POST /v1/responses`) | `gpt-6-luna` | `reasoning.effort = "high"` | C2 (Sonnet 5.5, high), C1 |
| **Y2** | Moonshot (Kimi), OpenAI-compatible API | Kimi K3: exact id recorded from that provider's `GET /v1/models` before any Y2 call | provider default, recorded | C2, C1 |

- **Y1 effort.** `high` matches the effort of C1 and C2. The model page (platform.openai.com,
  read 2026-10-04) lists `none, low, medium (default), high, xhigh, max`, and recommends the
  Responses API for function calling with reasoning.
- **Y2 is conditional.** The user's Kimi key is rate-limited at registration time. Y2 runs only
  after a dated entry in Deviations records:
  - the exact model id;
  - the endpoint;
  - the thinking setting;
  - any adapter difference.
  
  That entry must be made before its first call. The prompt, tools, seeds, metrics and decision
  rule below apply unchanged. If Kimi K3 cannot be called, Y2 is recorded as not run and is not
  replaced by another model.
- **Fixed references (read only, not re-run):**
  - C1 `experiments/results/20261003-2323_claude_strong` (Opus 5.5, high);
  - C2 `experiments/results/20261004-0049_claude_strong` (Sonnet 5.5, high);
  - the PassiveBayes and GoodScientist baselines in the frozen report.

## 3. What is held fixed (the adapter)

A new adapter in this directory makes the same requests as the frozen `ClaudeAgent`, in the other
provider's wire format. No frozen source file is edited.

- **Prompt.**
  - The system prompt is `mirage.lab.tools.SYSTEM_PROMPT`, sent verbatim as `instructions`.
  - The first user message is `render_observation(...)`, verbatim.
  - The no-tool reminder is the frozen `REMINDER` string.
  - The frozen `prompt_sha256` (`dc07da98…`) is recorded unchanged.
- **Tools.** Each entry of `TOOL_DEFINITIONS` maps 1:1 to a function tool: `name`, `description`,
  `parameters = input_schema` (byte-identical JSON) and `strict = true`. A second hash, of the
  provider-format tool list, is recorded in the manifest.
- **Tool choice.**
  - `tool_choice = "auto"` and `parallel_tool_calls = false`, matching C1/C2's `auto` with
    `disable_parallel_tool_use`.
  - If a response nevertheless contains more than one function call, they are executed in order
    until the episode finishes, exactly as the frozen loop does. Every call gets a result.
- **Limits.**
  - `max_output_tokens = 16000` per response;
  - at most 12 turns;
  - budget 6;
  - the same tool results, JSON-encoded with sorted keys, including `{"error": …}` on a
    rejected call.
- **Conversation state.**
  - The full input history is resent every turn, with `store = false`.
  - Reasoning items are passed back to the model as returned, using `include =
    ["reasoning.encrypted_content"]`, so the model keeps its own reasoning across turns as
    Claude does.
  - No prompt caching is configured.
- **Outcomes.**
  - A transport/HTTP error after the client's retries (4 retries with backoff on 429/5xx, 120 s
    timeout) is `API_FAILURE`, and the episode is re-run once by the frozen runner logic.
  - A `refusal` content item is `REFUSED`.
  - A response whose `model` is neither the configured id nor a dated snapshot of it
    (`<id>-YYYY-MM-DD`) is `API_FAILURE`. **No model is ever substituted.**
  - An `incomplete` response, or one without a function call, gets the frozen reminder.
- **Scoring.** The frozen `runner.run_episode`, `summarize` and evaluator are used unchanged. The
  records go through the frozen runner's `"claude"` LLM slot, the runner's only slot for model
  agents. The `model` field in every manifest and episode record identifies the actual model.

## 4. Seeds and procedure

1. **Dry run (pipeline check only, never reported as a result).** Y1 on development seeds 0 (BP)
   and 1 (MA), written to `.local/`, which is not committed. A driver bug found here is fixed
   before any strong-matrix episode; the prompt, tools and scoring never change.
2. **Scored run.** Y1 (then Y2, if available) on the **strong matrix**: seeds 500,000–500,029,
   15 BP and 15 MA, `experiments/configs/eval_matrix_v1.json`, through `runner.run`. Each
   (seed, configuration) is run once, apart from the runner's single API_FAILURE re-run, and both
   attempts are kept.
3. Records go to `experiments/exploratory/cross-family/runs/<run_id>/`: manifest, episodes,
   reruns, `usage.jsonl`, `summary.json` and `results.md`.

## 5. Metrics and decision rule

From the frozen evaluator, per configuration:

- M1, M2 and M3 as k/30, with Wilson 95 % intervals;
- M4 (mean, median and max units);
- Q1 (k/30);
- mean Brier;
- the same metrics per BP/MA block.

From `usage.jsonl`: tokens, calls and USD per episode.

**Failure classes**, the same as model-effort §5:

- justified;
- correct without control;
- wrong after a control;
- wrong without a control;
- NO_DIAGNOSIS;
- API_FAILURE;
- REFUSED.

The failed clauses are listed for every non-justified episode. s500028-BP is reported but not
re-scored (OPEN_RULINGS §H).

**Decision rules.** These are descriptive; there are no significance claims at n = 30
(EXPERIMENT_PLAN §10).

- **Control (primary):** "control retained" if M2's Wilson 95 % lower bound is above 0.65.
  Otherwise "control not retained".
- **M3 vs C2 (29/30):**
  - "detectable drop" if the upper bound is below C2's lower bound (0.833);
  - "lower, worth following up" if the intervals overlap but M3 ≤ 26/30;
  - otherwise "no detectable difference at n = 30", which is not a claim of equality.

## 6. Spend cap and pricing

- **Cap:** $2.00 per provider, dry runs included.
- **gpt-6-luna Standard prices** (platform.openai.com pricing and model page, read
  2026-10-04), per MTok: input $0.10, cached input $0.01, output $0.50. Reasoning tokens are
  billed as output. Requests stay far below the 272K-token long-context threshold.
- **Expected cost.** C2 used about 0.6 M input and 0.06 M output tokens over 30 episodes. At
  Luna prices that is about $0.10, so even 10× more tokens stays under the cap.
- **Before every call** the driver adds a worst-case estimate to a session ledger (previous
  input + 2,000 input tokens, plus 16,000 output tokens) and stops if the cap would be exceeded.
  A run stopped this way is reported as incomplete, never as a 30-episode result.
- Y2 prices are recorded in its Deviations entry before its first call.

## 7. Claims allowed

Only descriptive claims about these models, this scenario and these 30 episodes, compared with
C1, C2 and the frozen baselines on the same matrix:

- No claim about model families in general, or about which model is "better" outside this task.
- The prompt was written and tuned against Claude, so any gap may reflect that rather than a
  difference in capability.

## Deviations

None at registration time. Dated entries are appended below; the text above is not edited.
