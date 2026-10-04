# MIRAGE-Bio — Team Handoff

> **LEGACY: MIRAGE-Bio v0.1 (growth / OD600 benchmark).** This document is the historical record of the first, separate environment. Status lines, "not started" notes and plans below date from 3-4 October 2026 and were **not** updated; the growth benchmark has since been implemented and run (see [mirage-bio/README.md](README.md)). It does not describe the Binder rescue system. Current status: [START_HERE](../START_HERE.md).

```text
SPECIFICATION STATUS

MIRAGE-level methodology: documented
MIRAGE-Bio v0.1: pending Gate 0 validation
Implementation: not started
```

**Read this first.** It covers who does what now. Deadline: **Sunday 4 October 2026,
14:45 BST.**

Details:
- Project framing: [MIRAGE](../MIRAGE.md)
- [ANALYSIS](ANALYSIS.md): what and why
- [DESIGN](DESIGN.md): how
- [GATE0_SPEC](GATE0_SPEC.md): scientific validation
- [DEVELOPMENT_PLAN](DEVELOPMENT_PLAN.md): order
- [TEST_PLAN](TEST_PLAN.md)
- [EXPERIMENT_PLAN](EXPERIMENT_PLAN.md)
- [RISKS](RISKS.md)

---

## What we are building

MIRAGE-Bio, the first environment of MIRAGE. It is a controlled virtual microbiology
lab.

An AI scientist sees an OD600-like growth curve that rises and flattens. It must work
out: **did the cells stop growing, or did the instrument stop seeing them?** It can
request diluted measurements of retained aliquots on a budget of 6, then submits a
diagnosis. A deterministic evaluator scores both the answer and whether the agent
obtained evidence that justified it.

## What we are not building

- No generic MIRAGE framework, adapters or second environment. The general MIRAGE
  material is documentation only.
- No second assay, organism or domain. No real data or wet lab.
- No UI, no agent framework, no RAG, no multi-agent setup, no fine-tuning.
- No LLM judge.
- No more than 30 eval episodes. No second model before the evaluation freeze.

## Scientific core

| | `BIOLOGICAL_PLATEAU` | `MEASUREMENT_ARTIFACT` |
|---|---|---|
| Truth | Culture stops at $K = 0.80$–$0.90\,S$ | Culture grows to $K = 3$–$5\,S$ |
| Passive readings | Plateau ≈ true biomass (compression ≤ 4.4 %) | Plateau ≈ $S$, far below true biomass |
| Late sample diluted 1:10, back-corrected ÷ passive plateau | ≈ 1.03 | ≈ 3–5 |

**Model**
- Growth is Richards: $X^{-8}(t) = K^{-8} + (X_0^{-8} - K^{-8})e^{-8rt}$.
- The assay reads $f(x) = x[1+(x/S)^8]^{-1/8}$, plus noise $0.003 + 0.02y$.
- $S$ is unknown to the agent and varies per episode (0.5–2.0, log-uniform). It is
  independent of the condition and fixed within the episode.
- Both conditions give exactly the same curve family; only the plateau level
  differs. The analytic passive ceiling is ≈ 0.58.

**Agent-facing rules**
- The agent answers `BIOMASS_AS_READ` or `BIOMASS_ABOVE_READING`. Condition names never
  reach it.
- The scored prompt never asks the agent to list hypotheses. `declare_state` is
  optional.

**Scoring**
- A **diagnostic control** (M2) must meet all four conditions:
  1. accepted, and taken before the diagnosis;
  2. diluted ($d > 1$);
  3. taken from the fixed late window $t \in [12, 18]$ h;
  4. with a dilution factor in the Gate-0-frozen diagnostic set $D_{\text{diag}}$.
- It does **not** need to be in the useful region.
- **Reconstruction adequacy** (Q1, secondary) separately records whether the sample
  was in the useful region (≤ 5 % compression, reading ≥ 0.03), i.e. whether the
  biomass estimate is accurate.
- Key example: late 1:2 is diagnostic but quantitatively inaccurate. Late 1:10 is
  both.
- Metrics:

  | Metric | Meaning |
  |---|---|
  | M1 | Accuracy |
  | M2 | Diagnostic-control rate |
  | M3 | Justified accuracy (M1 ∧ M2) |
  | M4 | Cost |
  | M5 | Diagnosticity (stretch only) |

## Critical path

```text
MS0 Gate 0 (Sat 18:00 target, 18:30 hard) → MS1 lab (Sat 21:30) → MS2 Claude + prompt freeze (Sat 23:30)
→ MS3 first 10 episodes (Sun 01:00, latest 09:30) → MS4 eval freeze (Sun 11:30, hard)
→ MS5 demo (Sun 13:00) → code freeze 13:30 → MS6 submitted (Sun 14:15) → deadline 14:45
```

## Gate 0 (blocking; authority: [GATE0_SPEC](GATE0_SPEC.md))

**Checks** that must pass:
- passive classifiers ≤ 0.65;
- Condition A is not saturated, and dilution recovers it within ±15 %;
- 1:10 late dilution separates B ($R \ge 2.5$), with `GoodScientist` ≥ 0.98;
- undiluted and early samples are non-diagnostic;
- exact curve-family equivalence holds;
- $S$ is independent of the condition and stable within an episode;
- the diagnostic dilution set $D_{\text{diag}}$ for M2 is frozen (G0-H).

Reported, non-blocking: 1:2 reconstruction bias (1:2 is diagnostic but
quantitatively inaccurate); robustness.

**Outputs** in `experiments/results/gate0/`:
- `assay_response.png`
- `passive_overlap.png`
- `latent_reveal.png`
- `intervention_sweep.png`
- `separability_before_after.png`
- `robustness_map.png` (non-blocking)
- `summary.json`

Compare against the design-time reference in `experiments/reference/`. That
reference is not Gate 0. **No LLM code merges before Gate 0 passes.** Thresholds are
fixed: do not tune them after seeing numbers, and never retune the benchmark after
seeing Claude's results.

## Team roles

| Role | Owns | First tasks |
|---|---|---|
| **Science lead** (SCI) | Gate 0 and the parameter freeze (including $D_{\text{diag}}$); diagnostic-control rule; claims | DEV-002 to DEV-006 |
| **Environment lead** (ENV) | Simulator and lab against the frozen interfaces; runner; scripted agents | DEV-001; DEV-007a visible interface by 16:00; DEV-007, 009, 010 |
| **Agent lead** (AGT) | Minimal Claude tool loop; never sees hidden state | DEV-012 against a mock `LabSession` |
| **Evaluation & demo lead** (EVD) | Record schemas, metrics, replay, results, pitch | DEV-008a record schemas + fixture by 16:00, then DEV-008 and DEV-017 against fixture logs |
| QA (5-person team only) | Trust-boundary tests, merges, submission | DEV-011, DEV-019 |

**No one waits for the Claude integration to build evaluation or replay.** EVD works
from fixture records. AGT works from a mock session. Split plans for 3, 4 and 5
people: [DEVELOPMENT_PLAN §6](DEVELOPMENT_PLAN.md#6-team-allocation).

## Current priorities (now → 18:30 Saturday)

1. Freeze the docs at 15:00. Create GitHub issues from DEV-001 to DEV-019 and
   milestones MS0–MS6. MIRAGE-level docs create no issues.
2. By 16:00:
   - DEV-001 skeleton;
   - DEV-007a (`lab/tools.py`, `agents/base.py`);
   - DEV-008a (record schemas + `tests/fixtures/sample_episode_llm.json`).
3. SCI: DEV-002 to DEV-006, ending in Gate 0.
4. AGT: Claude adapter against the mock. Tests use a mocked client.
5. EVD: evaluator and replay against the fixture.

## Definition of done (every PR)

- Linked to one DEV task. Touches only that task's files.
- Relevant tests from TEST_PLAN added and passing. Command output pasted in the PR.
- No hidden-module imports in `agents/` or `lab/tools.py`.
- No secrets. No hand-typed result numbers.
- Docs updated if a contract changed. Interface or schema changes need ENV, AGT and
  EVD agreement.

## Do-not-do list

- Do not mention saturation, artefact, linear range, plateau, ceiling or the
  condition names in anything the agent sees.
- Do not ask the agent to enumerate hypotheses or alternatives.
- Do not edit the prompt after the 23:30 freeze, or ever on eval seeds.
- Do not re-run eval episodes to get a better result. Only `API_FAILURE` gets one
  re-run.
- Do not use an LLM in scoring. Do not substitute another model on a refusal.
- Do not call `PassiveBayes` optimal. Do not claim a U-shaped dilution optimum.
- Do not claim biological findings, universal OD thresholds, "first" status or
  generalisation.
- Do not commit `.env`, API keys, or raw request headers.

## Stop rules (short form)

- No LLM merge before Gate 0.
- No generic MIRAGE adapters or second environment.
- No second assay, organism, world or condition.
- No framework, RAG or UI. No Modal.
- No second model before MS4. ≤ 30 eval episodes.
- No threshold or parameter changes after results.
- After 13:30 Sunday, docs only.

Full list: [DEVELOPMENT_PLAN §8](DEVELOPMENT_PLAN.md#8-stop-rules).

## Demo story (≤ 3 minutes)

1. **Hook** (`latent_reveal.png`): two identical growth curves. "One culture stopped
   growing. The other kept growing 4× beyond what the reader shows. Which is which?"
2. **The MIRAGE idea:** the answer is deliberately unknowable from the readings.
   Does the AI know what experiment would make it knowable? The analytic passive
   ceiling is ≈ 58 % (`separability_before_after.png`).
3. **Replay:** Claude picks a measurement (time, dilution), gets new evidence, and
   diagnoses. It may record notes along the way. Then the reveal: true biomass,
   M2/Q1 audit, score.
4. **Results table:** Claude vs `PassiveBayes` vs `GoodScientist` (M1–M4, Wilson
   intervals). Correct and justified are shown separately.
5. **Integrity:** synthetic world, hidden ground truth, frozen before agent runs, no
   LLM judge, every number recomputable.

## Commands

| Command | State |
|---|---|
| `git clone https://github.com/Pimentellll/originator-science.git && cd originator-science` | works now |
| `python3 experiments/reference/design_validation.py [--quick]` (stdlib only; design-time reference, **not** Gate 0) | works now |
| `python -m venv .venv && source .venv/bin/activate` | works now |
| `pip install -e ".[dev]"` | **planned** (DEV-001) |
| `pytest` | **planned** |
| `python scripts/gate0.py --config experiments/configs/scenario_v1.json --out experiments/results/gate0` | **planned** (DEV-006) |
| `python -m mirage.evaluation.runner run --agent good_scientist --matrix experiments/configs/eval_matrix_v1.json --out experiments/results/<run_id>` | **planned** (DEV-009) |
| `python -m mirage.evaluation.runner run --agent claude --matrix … --out …` (needs `ANTHROPIC_API_KEY`) | **planned** (DEV-012) |
| `python -m mirage.evaluation.runner summarize experiments/results/<run_id>` | **planned** (DEV-009) |
| `python -m mirage.demo.replay experiments/results/demo/<episode>.json --figure out.png` | **planned** (DEV-017) |
