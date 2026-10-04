# Pre-registration: measurement-price sensitivity (exploratory)

| Field | Value |
|---|---|
| Status | **Exploratory, not confirmatory.** Registered 2026-10-04, before any paid API call and before any result in this directory was computed. |
| Branch | `exp/cost-sensitivity` (off `main` at `d56cb1a`) |
| Scope | MIRAGE-Bio v0.1 growth benchmark, `scenario-v1`, frozen Gate 0 `D_diag`, unmodified evaluator |
| Frozen inputs read, never written | `src/mirage/{lab,evaluation,agents,environments,rl}/`, `src/mirage/config.py`, `experiments/configs/`, `experiments/results/`, `results/`, `experiments/preregistration/`, `docs/mirage-bio/` |

## 1. Question

At what measurement price does Claude Sonnet 5.5 stop running the diagnostic control, and
does its stated confidence drop when it skips the control?

## 2. Hypotheses

- **H-price.** Under prompt-v2 the diagnostic control stays affordable at every registered
  price, and units left unspent have no value to the agent, so Sonnet keeps running the control
  at all three prices. That is, there is no stopping price in {1×, 3×, 6×}.
  *Alternative:* the control rate (M2) falls as the price rises, most visibly at 6×, where one
  replicate uses the whole budget.
- **H-conf.** In episodes where no diagnostic control is run, the stated probability is less
  extreme (closer to 0.5) than in episodes where it is run.
- **H-lucky.** If controls are skipped, correct answers without a control (M1 ∧ ¬M2, "lucky
  correct") become more frequent.

## 3. Design: what "price" means here

In the frozen environment (`src/mirage/lab/environment.py`, `src/mirage/lab/tools.py`), the
budget is `BUDGET_UNITS = 6`, and one `measure_od` replicate costs 1 unit. The agent is told this in
three places: the system prompt ("each replicate reading costs 1 unit from a budget of 6 units"),
the `measure_od` tool description ("costs 1 budget unit") and the first observation
(`budget.cost = "1 unit per replicate reading"`).

**Chosen design: a higher unit price against the same 6-unit budget.** At price *c*, one replicate
costs *c* units, the budget stays 6 units, and the number of affordable replicates is ⌊6/c⌋.

| Level | Units per replicate *c* | Budget (units) | Replicates affordable |
|---|---|---|---|
| 1× | 1 | 6 | 6 (identical to C2 apart from the driver) |
| 3× | 3 | 6 | 2 |
| 6× | 6 | 6 | 1 (the level at which only one replicate is affordable) |

Why this design and not the alternatives:

- *A proportionally scaled budget* (cost *c*, budget 6*c*) changes only the label. What the agent
  can afford does not change, so it tests wording, not price.
- *An explicit penalty or money cost stated in the prompt* adds a second objective that the
  evaluator does not score. That changes the task, not just the price.
- *A fixed budget with a higher unit price* is the ordinary meaning of a price increase. The only
  thing that changes is what a replicate costs out of the same budget. The smaller number of
  affordable replicates follows directly from the price; it is not a separate manipulation.

**The M2 definition still applies unchanged.** A diagnostic control (DESIGN §15, `audit_measurements`)
is any accepted, pre-diagnosis, late (12–18 h), diluted measurement with dilution in `D_diag` =
[1.1, 100]. `D_diag` was evaluated with 1 replicate (`evaluated_replicates = 1`), so one replicate is
a full control. A control is affordable at every registered price. The evaluator, audit and record
schema are not modified. `scores.cost_units` (M4) keeps its frozen meaning, the number of
replicates. The driver also reports priced units = *c* × replicates.

What the driver changes for *c* > 1, and nothing else:

1. The three cost strings above are re-rendered with *c* (for example "costs 3 units from a budget of
   6 units", "costs 3 budget units", "3 units per replicate reading").
2. Budget accounting: an accepted request deducts *c* × replicates. A request costing more than the
   remaining units is rejected with an error and uses a turn, like the frozen over-budget error.
3. The `budget_remaining` values returned to the agent are in units.
4. The record labels: `prompt_version = "prompt-v2-price{c}x"`, with `prompt_sha256` computed over the
   priced system prompt and tools in the frozen way. The manifest also records
   `unit_price`, `budget_units` and `driver`.

At *c* = 1, the system prompt, tools, first observation, `prompt_version` (`prompt-v2`),
`prompt_sha256` (`dc07da98…d91d1`), request parameters and environment behaviour are
bit-identical to the frozen C2 configuration. The driver's tests check this.

The adapter loop, model, effort and limits are those of `ClaudeAgent`: `claude-sonnet-5-5`, effort
`high`, `MAX_TOKENS` 16000, at most 12 turns, `disable_parallel_tool_use`, no model fallback. All
driver code is under `experiments/exploratory/cost-sensitivity/`. It imports or subclasses the
frozen classes and edits no file under `src/`.

## 4. Configurations, seeds and order

| ID | Agent | Price | Matrix | Episodes |
|---|---|---|---|---|
| X-P1 | Claude `claude-sonnet-5-5`, effort high | 1× | strong (seeds 500000–500029, 15 BP + 15 MA, `eval_matrix_v1.json`) | 30 |
| X-P3 | same | 3× | strong | 30 |
| X-P6 | same | 6× | strong | 30 |
| G-P{1,3,6} | positive control, scripted (no API): GoodScientist's rule (1:10 at 18 h, R ≥ τ = 1.5) with replicates = min(3, ⌊6/c⌋) | 1×, 3×, 6× | strong | 30 each |

- **Dry run first (never reported as results).** Four development-seed episodes: seed 0 BP at 1×,
  seed 1 MA at 3×, seed 2 BP at 6× and seed 3 MA at 6×. This is a pipeline and cost check only.
- **Scored order:** X-P6, then X-P3, then X-P1 (the most informative arm first), each over the
  30 episodes in matrix order.
- Each (seed, configuration) is run once. An `API_FAILURE` episode is re-run once, and both
  attempts are kept (the frozen runner's `reruns/` convention).
- Reference, not re-run: C2 (`experiments/results/20261004-0049_claude_strong`, the same model,
  effort, prompt and matrix). It is only compared descriptively with X-P1.

## 5. Metrics

Per arm, from the existing `summarize` (`summary.json`) and `mirage.evaluation.report` (`results.md`):

- M1 (correct), M2 (diagnostic control), M3 (justified) as k/n with Wilson 95% intervals;
- M4 (replicates: mean, median, max), priced units (mean), Q1, mean Brier, status counts.

Secondary, computed by the driver's analysis script from the episode records:

- **Lucky correct:** the number of episodes with M1 ∧ ¬M2, as k/n with a Wilson 95% interval.
- **Confidence when a control is skipped:** confidence = max(p, 1 − p) and the Brier score, split by
  M2 (control vs no control), per arm and pooled over the three Claude arms.
- Number of measure calls, and whether any request was rejected for exceeding the budget.

## 6. Decision rules (all descriptive; no significance claims at n = 30)

- **Stopping price:** the lowest registered price with M2 ≤ 15/30 (at most half of episodes run
  a control). If there is none, "no stopping price within 1×–6×".
- **Detectable change in control rate at price c:** the Wilson 95% intervals of M2(c) and M2(1×)
  do not overlap. Otherwise it is reported as "no detectable change", never as "equal".
- **H-conf:** evaluated only if there are at least 5 no-control episodes pooled across the Claude
  arms. "Lower confidence when skipping" means that the mean confidence of no-control episodes is
  at least 0.10 below that of control episodes. Otherwise it is reported as not supported, or as
  untestable when there are fewer than 5 such episodes.
- **H-lucky:** lucky-correct k/n per arm with Wilson intervals; "increase" only if the 6× interval
  does not overlap the 1× interval.
- **Validity guard:** if the scripted positive control G-P{c} has M3 < 0.95 at any price, the Claude
  results at that price are flagged as possibly reflecting task difficulty, not agent choice.

## 7. Spend cap

- Cap: **$5.00** of Anthropic API usage for the whole session, including the dry run.
- Pricing (platform.claude.com/docs/en/about-claude/pricing, fetched 2026-10-04): Claude Sonnet 5.5
  costs $2 per MTok of input and $10 per MTok of output (cache writes $2.50/MTok for 5 minutes, cache hits
  $0.20/MTok; the adapter does not use caching).
- Estimate: the C2 run used 303,003 input and 30,390 output tokens, so about $0.91 for 30 episodes, with
  at most $0.048 for one episode. Three arms plus the dry run are projected at about $2.9 at most.
  Higher prices allow fewer measurements, so they should need fewer turns.
- Accounting: every API response's `usage` is appended to the run's `usage.jsonl`, in the format of the
  committed runs. Spend = Σ (input × $2 + output × $10) / 10⁶, plus cache terms if any.
- **Stop rule:** before each episode, the driver sums the spend over every `usage.jsonl` under this
  directory. If that sum plus a $0.15 reserve exceeds $5.00, it stops. An arm cut short is reported
  as incomplete, on its completed prefix (the matrix interleaves BP and MA).
- **Pre-registered fallback:** if the dry run projects the three full arms above $4.50, X-P1 is reduced
  to the balanced minimal prefix (seeds 500000–500009, 5 BP + 5 MA), and X-P6 and X-P3 stay full.

## 8. Allowed and forbidden claims (EXPERIMENT_PLAN §10)

- Allowed: "In this scenario, with `claude-sonnet-5-5`, effort high and prompt-v2 priced at c×, M2 was
  k/n [Wilson 95% CI] …", and descriptive differences between prices.
- Forbidden: significance claims; claims beyond this scenario, configuration and sample;
  comparisons with models not run on this matrix with this driver; any re-scoring of the frozen runs
  (including s500028-BP, OPEN_RULINGS §H).
- Not tested: prices at which the control is unaffordable (*c* > 6), where M2 = 0 by construction.

## Deviations

None yet. Any later deviation is added here with a date and is never edited into the sections above.
