# MIRAGE-Bio — Test Plan

| Field | Value |
|---|---|
| Status | Accepted for MVP (3 October 2026). No tests are implemented yet. Inventory: T-001 to T-031. |
| Role | **How we verify** that the implementation meets [ANALYSIS](ANALYSIS.md) and [DESIGN](DESIGN.md) |
| Related | [GATE0_SPEC](GATE0_SPEC.md) (scientific criteria) · [DEVELOPMENT_PLAN](DEVELOPMENT_PLAN.md) (which milestone needs which tests) · [EXPERIMENT_PLAN](EXPERIMENT_PLAN.md) |

---

## 1. Strategy

- **Unit** tests check pure functions and validators, are exact where maths allows,
  and run in milliseconds.
- **Integration** tests check component boundaries: environment ↔ agent,
  evaluator ↔ records, adapter ↔ (mocked) API, trust boundary.
- **Scientific-validation** tests check SVR properties on seeded simulated
  populations. In `pytest` they use reduced sample sizes. Gate 0
  (`scripts/gate0.py`) repeats them at full size with the same thresholds.
- **End-to-end** tests run agents through the runner and check aggregate metrics
  and replay.

Rules:
- Every test is deterministic (fixed seeds) and runs **without network**. The Claude
  adapter is tested with a mocked client.
- The whole `pytest` suite should finish in < 60 s.
- Tests must not be weakened or deleted to make a change pass. A threshold change
  requires a DESIGN update and science-lead approval.
- Scientific-validation tests carry the `science` marker. `pytest -m science` runs
  them alone.

Sample sizes in `pytest` are chosen so the expected value lies well inside the
threshold. For example, G0-A expects ≈ 0.58 against a 0.65 threshold; at 500 per
condition the standard error is ≈ 0.016.

## 2. Test inventory

| ID | Title | Category | Traces to | Milestone |
|---|---|---|---|---|
| T-001 | Simulator determinism | Unit | NFR-001, DESIGN §18 | MS0 |
| T-002 | Logistic / Richards growth analytic sanity | Unit | FR-001, DESIGN §5.2 | MS0 |
| T-003 | Biological plateau reaches configured carrying capacity | Unit | FR-002 | MS0 |
| T-004 | Biological condition remains inside the intended measurement regime | Scientific-validation | SVR-003, G0-B | MS0 |
| T-005 | Measurement-artifact condition has latent biomass well above its apparent plateau | Scientific-validation | FR-003, SVR-007, G0-C | MS0 |
| T-006 | Low-density assay response is approximately linear | Unit | FR-005, A-008 | MS0 |
| T-007 | High-density assay response becomes sublinear | Unit | FR-005, A-008 | MS0 |
| T-008 | Passive ambiguity passes the quantitative criterion | Scientific-validation | SVR-001, G0-A | MS0 |
| T-009 | Adequate dilution reconstructs Condition A near its true plateau | Scientific-validation | SVR-003, G0-B | MS0 |
| T-010 | Adequate dilution strongly separates Condition B | Scientific-validation | SVR-002, G0-C | MS0 |
| T-011 | Dilution changes the aliquot only | Unit | FR-007, A-012, A-013 | MS1 |
| T-012 | Hidden configuration cannot reach the agent | Integration | SVR-004, SVR-005, NFR-005 | MS1/MS2 |
| T-013 | Budget accounting | Unit | FR-008 | MS1 |
| T-014 | Diagnosis scoring | Unit | FR-011, FR-013, M1, M3 | MS1 |
| T-015 | `GoodScientist` baseline succeeds | End-to-end | SVR-002, FR-018, MVP criteria | MS1 |
| T-016 | Passive baseline behaves as predicted | End-to-end | SVR-001, FR-018 | MS1 |
| T-017 | Episode log is reproducible | Integration | NFR-001, FR-014 | MS1 |
| T-018 | Offline replay reproduces a saved episode | End-to-end | FR-016, NFR-006, DR-001 | MS5 |
| T-019 | Passive-family equivalence | Scientific-validation | DESIGN §5.4, G0-E | MS0 |
| T-020 | Request validation and error semantics | Unit | FR-009, DESIGN §19 | MS1 |
| T-021 | Diagnostic-control validity rule | Unit | SVR-007, M2, DESIGN §15 | MS1 |
| T-022 | Claude adapter loop with mocked client | Integration | FR-010, DESIGN §9.4, §19 | MS2 |
| T-023 | Summary recomputation and Wilson intervals | Integration | NFR-002, FR-015, ER-006 | MS1 |
| T-024 | Same seed gives the same nuisance parameters in both conditions | Unit | SVR-006, FR-004 | MS0 |
| T-025 | Nuisance independence: distribution of $S$ is independent of the condition | Scientific-validation | SVR-006, G0-F | MS0 |
| T-026 | Within-episode instrument stability | Unit | SVR-006, A-009, G0-F | MS1 |
| T-027 | Visible late window: lateness does not depend on hidden state | Unit | SVR-007, A-021 | MS1 |
| T-028 | Scored prompt does not scaffold competing hypotheses | Integration | FR-019, SVR-004 | MS2 |
| T-029 | Gate 0 summary integrity | Integration | FR-017, GATE0_SPEC §7 | MS0 |
| T-030 | Gate 0 plot generation | Integration | FR-017, GATE0_SPEC §3 | MS0 |
| T-031 | Changed scientific configuration invalidates Gate 0 results | Integration | ER-005, ER-007, GATE0_SPEC §8 | MS1 |

By category:
- **Unit:** T-001, T-002, T-003, T-006, T-007, T-011, T-013, T-014, T-020, T-021,
  T-024, T-026, T-027.
- **Integration:** T-012, T-017, T-022, T-023, T-028, T-029, T-030, T-031.
- **Scientific-validation:** T-004, T-005, T-008, T-009, T-010, T-019, T-025.
- **End-to-end:** T-015, T-016, T-018.

## 3. Test specifications

Notation follows DESIGN §5. "Reference protocol" means DESIGN §16.1 steps 2–4
($t = 18$ h, $d = 10$, 3 replicates, $R = \hat C/\hat P$). BP = `BIOLOGICAL_PLATEAU`;
MA = `MEASUREMENT_ARTIFACT`.

### T-001 — Simulator determinism (unit)
- **Procedure.**
  1. Sample `EpisodeConfig` for seed 123 under each condition, twice.
  2. Generate passive histories.
  3. Issue the same request sequence twice, including one rejected request in the
     middle.
- **Acceptance.**
  - Configs, passive readings and measurement readings are identical across
    repeats.
  - A rejected request consumes no noise stream: the next accepted request's
    readings equal those obtained without the rejected request.
  - Seed 124 gives different readings.

### T-002 — Logistic / Richards growth analytic sanity (unit)
- **Procedure.**
  1. For $\nu = 1$, compare the closed form with $K/[1 + (K/X_0 - 1)e^{-rt}]$ on a
     grid.
  2. For $\nu \in \{1, 8\}$, compare the central finite-difference derivative with
     $rX[1-(X/K)^\nu]$.
  3. Check $X(0) = X_0$, monotonicity, and $X < K$.
- **Acceptance.**
  - Relative error ≤ 10⁻¹² for the closed-form comparison and ≤ 10⁻⁵ for the ODE
    residual.
  - $X(0) = X_0$ to 10⁻¹².
  - Strictly increasing for $X_0 < K$.

### T-003 — Biological plateau reaches configured carrying capacity (unit)
- **Procedure.** For 1,000 sampled BP configs, evaluate $X$ at 12 h (the start of
  the late window) and at 18 h.
- **Acceptance.** $X(18)/K \ge 0.9999$ and $X(t) \le K$ for all $t$ in 100 % of
  configs.

### T-004 — Biological condition inside the intended measurement regime (scientific-validation)
- **Procedure.** For 10,000 sampled BP configs, compute the compression
  $1 - f(K)/K$ and $K/K'$.
- **Acceptance.** Maximum compression ≤ 0.05, $K \le x_{\text{lin}}(S)$, and
  $K/K' \le 1.053$ in 100 % of configs. Design-time maximum compression: 0.0438.

### T-005 — MA latent biomass well above apparent plateau (scientific-validation)
- **Procedure.** For 10,000 sampled MA configs, compute $X(18)/K'$ and
  $X(12\text{ h})/K'$. For both conditions, compute $t_{95}$.
- **Acceptance.**
  - $X(18)/K' \ge 2.95$ and $X(12\text{ h})/K' \ge 2.5$ in 100 % of MA configs.
    Design-time minimum at 12 h: 2.995.
  - $t_{95} + 2\text{ h} \le 12$ h in 100 % of configs (window validity).
    Design-time maximum: 11.92 h.

### T-006 — Low-density assay response approximately linear (unit)
- **Procedure.** Evaluate the compression on $x/S \in [10^{-4}, 0.733]$.
- **Acceptance.**
  - Compression ≤ 0.001 for $x \le 0.5S$ and ≤ 0.01 for $x \le 0.733S$.
  - $f(x)/x \to 1$ as $x \to 0$ (≤ 10⁻⁹ at $x = 10^{-3}S$).

### T-007 — High-density assay response becomes sublinear (unit)
- **Procedure.** Evaluate $f$ on $x/S \in [0.5, 10]$.
- **Acceptance.**
  - $f$ is strictly increasing, $f(x) < S$, and $f(x)/x$ is strictly decreasing.
  - Compression at $2S$ lies in $[0.49, 0.51]$.
  - The finite-difference slope at $3S$ is < 10⁻³.
  - $x_{\text{lin}}/S = 0.9187 \pm 10^{-4}$.

### T-008 — Passive ambiguity (scientific-validation)
- **Procedure.**
  1. Analytic ceiling from 100,000 $\log K'$ draws per condition (pytest size).
  2. `PassiveBayes` (reference built from the `passive_reference` block, reduced to
     50,000 per condition in pytest) on 500 test episodes per condition (gate0 test
     seeds).
  3. 15-NN on log trajectories: 500 train and 500 test per condition.
- **Acceptance.** All three balanced accuracies ≤ 0.65 (the SVR-001 threshold).
  Gate 0 repeats this at full size.

### T-009 — Adequate dilution reconstructs Condition A (scientific-validation)
- **Procedure.** Reference protocol on 500 BP episodes.
- **Acceptance.** ≥ 95 % with $\lvert R - 1\rvert \le 0.15$ and ≥ 95 % with
  $\lvert \hat C/K - 1\rvert \le 0.15$. Design-time: $R$ 99th percentile 1.13;
  $\hat C/K$ central 95 % [0.93, 1.07].

### T-010 — Adequate dilution separates Condition B (scientific-validation)
- **Procedure.** Reference protocol on 500 MA episodes.
- **Acceptance.** ≥ 99 % with $R \ge 2.5$ and ≥ 95 % with $\lvert\hat C/K - 1\rvert \le 0.15$.
  Design-time: minimum $R$ 2.80.

### T-011 — Dilution changes the aliquot only (unit)
- **Procedure.**
  1. In one environment, request $(t = 18, d = 10)$, then $(t = 18, d = 1)$, then
     $(t = 12, d = 4)$.
  2. Compare the audit's noise-free values with those from fresh environments
     receiving each request alone.
- **Acceptance.**
  - Noise-free presented biomass and readings are identical regardless of request
    order or history.
  - The latent $X(t)$ is unchanged by any request.
  - Presented biomass equals $X(t)/d$ exactly.

### T-012 — Hidden configuration cannot reach the agent (integration)
- **Procedure.**
  1. **AST scan.** Modules under `mirage/agents/` and `mirage/lab/tools.py` import
     nothing from `mirage.config`, `mirage.biology`, `mirage.assay`,
     `mirage.evaluation` or `mirage.lab.environment`. Modules under
     `mirage/evaluation/` do not import `anthropic`.
  2. **Prompt-leakage scan.** For 200 episodes (100 per condition), render the
     system prompt, tool definitions, initial observation and every tool result
     produced by `GoodScientist`. Search case-insensitively for the forbidden terms
     of DESIGN §12.
  3. **Whitelist.** The initial observation's key set equals DESIGN §10.
  4. **Payload scan.** Using the mocked Anthropic client, capture every request
     payload. Assert that it contains no forbidden term, and that neither $K$ nor
     $S$ appears formatted to 6 significant figures.
- **Acceptance.** No violations.

### T-013 — Budget accounting (unit)
- **Procedure.** Request sequences with replicates (3, 2, 2): the third exceeds the
  remaining budget of 1. Follow with (1). Include invalid requests interleaved.
- **Acceptance.**
  - Charges are 3, 2, rejected (0), 1. `budget_remaining` is reported correctly
    after each.
  - Total charged ≤ 6. Invalid or rejected requests charge 0.
  - The passive history charges 0.

### T-014 — Diagnosis scoring (unit)
- **Procedure.** Build synthetic records covering every combination of {BP, MA} ×
  {`GROWTH_STOPPED`, `GROWTH_CONTINUED`, none} × {valid control, no valid control}.
- **Acceptance.**
  - Mapping as in DESIGN §9.1.
  - `correct`, `valid_control` and `justified` follow the truth table; a missing
    diagnosis is incorrect.
  - Brier equals $(p - y)^2$.
  - M1–M4 over a synthetic set equal hand-computed values.

### T-015 — `GoodScientist` baseline succeeds (end-to-end)
- **Procedure.** Runner with `GoodScientist` on 300 episodes per condition (pytest);
  1,000 per condition at MS1.
- **Acceptance.** M1 ≥ 0.98, M2 = 1.00, M3 ≥ 0.98 (MVP requires ≥ 0.95), M4 = 3.00,
  on every subset by condition.

### T-016 — Passive baseline behaves as predicted (end-to-end)
- **Procedure.** Runner with `PassiveBayesAgent` on 300 episodes per condition
  (pytest); 1,000 per condition at MS1.
- **Acceptance.**
  - Balanced M1 ∈ [0.50, 0.65], and within ±0.05 of the G0-A `PassiveBayes` value
    where available.
  - M2 = M3 = 0. M4 = 0. No `measure_od` events.

### T-017 — Episode log is reproducible (integration)
- **Procedure.**
  1. Run `GoodScientist` on 20 episodes twice into two directories.
  2. Re-score each record from its own contents.
- **Acceptance.**
  - Records are byte-identical after removing `run_meta`.
  - Re-scored `audit` and `scores` equal the stored ones.

### T-018 — Offline replay reproduces a saved episode (end-to-end)
- **Procedure.**
  1. Replay a committed fixture record (`tests/fixtures/sample_episode_llm.json`)
     and a freshly produced `GoodScientist` record, with networking disabled
     (monkeypatched `socket.socket`) and `ANTHROPIC_API_KEY` unset.
  2. Capture the output.
- **Acceptance.**
  - Exit code 0.
  - Steps appear in event order.
  - The revealed condition, $K$, $S$ and back-corrected values equal those
    recomputed from the record.
  - `--figure` writes a PNG.

### T-019 — Passive-family equivalence (scientific-validation)
- **Procedure.** For 1,000 configs per condition, on $t = 0, 0.25, \dots, 18$,
  compare $f(X(t))$ with the Richards curve with parameters $(K', y_0, r, \nu)$.
- **Acceptance.** Maximum relative deviation ≤ 10⁻⁹.

### T-020 — Request validation and error semantics (unit)
- **Procedure.** Submit invalid inputs:
  - `time_h` ∈ {−1, 19, 2.5, "18"};
  - `dilution_factor` ∈ {0.5, 0, 101, NaN};
  - `replicates` ∈ {0, 4};
  - extra field; missing field; unknown tool name;
  - `submit_diagnosis` with an invalid label.
- **Acceptance.**
  - Each input returns an error response, logged as `ok = False`, with no charge
    and no noise-stream consumption, counting as a turn.
  - The environment state is otherwise unchanged.

### T-021 — Diagnostic-control validity rule (unit)
- **Procedure.** Use the matched demo pair configs (late window $[12, 18]$ h) and
  synthetic event lists.

  | Case | Condition | $t$ | $d$ | Expected | Failing clause |
  |---|---|---|---|---|---|
  | a | MA | 4 | 10 | invalid | not late |
  | b | MA | 18 | 1 | invalid | not diluted |
  | c | MA | 18 | 2 | invalid | outside useful region |
  | d | BP | 18 | 50 | invalid | below LoQ |
  | e | BP | 18 | 10 | valid | — |
  | f | MA | 18 | 10 | valid | — |
  | g | MA | 12 | 10 | valid | — (window start) |
  | j | MA | 11 | 10 | invalid | not late (informative, but outside the fixed window) |
  | h | MA | 18 | 10, logged after the diagnosis event | invalid | after diagnosis |
  | i | BP | 18 | 2 | valid | — (BP genuinely in region; DESIGN §15 asymmetry) |

- **Acceptance.** Validity and the recorded failing clause match the table.

### T-022 — Claude adapter loop with mocked client (integration)
- **Procedure.** Inject a fake client returning scripted responses:
  - (1) a `tool_use` for `declare_state`, then `measure_od`, then
    `submit_diagnosis`;
  - (2) `end_turn` without a tool call, then a tool call;
  - (3) `stop_reason = "refusal"`;
  - (4) an `APIConnectionError` on every call;
  - (5) 12 turns of `measure_od` with invalid arguments;
  - (6) a response whose `model` differs from the configured one.
- **Acceptance.**
  - (1) `DIAGNOSED`; each tool result is returned in the next user message; the
    full `response.content` is appended unchanged.
  - (2) Exactly one reminder message, and the turn is counted.
  - (3) `REFUSED`.
  - (4) `API_FAILURE` after the configured retries.
  - (5) `NO_DIAGNOSIS` at turn 12.
  - (6) `API_FAILURE` with reason.
  - Every request has `tool_choice = {"type": "auto", "disable_parallel_tool_use": true}`,
    `output_config.effort = "high"`, and no `temperature`, `top_p` or `thinking`
    disable flag.
  - The transcript is stored in `llm_transcript`.

### T-023 — Summary recomputation and Wilson intervals (integration)
- **Procedure.**
  1. Run `summarize` on a run directory and on a copy of it.
  2. Compute Wilson intervals for known cases.
- **Acceptance.**
  - Output is byte-identical to the committed `summary.json`.
  - Wilson 95 % for 8/10 is [0.4902, 0.9433] (±10⁻⁴); for 0/10 it is [0.0000, 0.2775];
    for 10/10 it is [0.7225, 1.0000].
  - Primary and intention-to-treat denominators are handled as in DESIGN §15.

### T-024 — Same seed gives the same nuisance parameters (unit)
- **Procedure.** For seeds 0–999, sample under both conditions.
- **Acceptance.**
  - $S$, $r$, $X_0$, $\nu$ and the full `AssayConfig` are identical across
    conditions.
  - $K$ differs, with $\kappa$ and $\lambda$ at the same quantile of their ranges.
  - One assay code path is used: the condition is not an argument of any
    `assay.od_reader` function.

### T-025 — Nuisance independence (scientific-validation)
- **Procedure.**
  1. Sample 10,000 episodes per condition with **independent** seed sets
     (BP: 0–9,999; MA: 10,000–19,999).
  2. Compute the two-sample KS statistic of $\log S$, $r$ and $\log X_0$ between
     conditions.
  3. Inspect the sampler: nuisance draws precede any read of the condition.
- **Acceptance.** Each KS statistic ≤ 0.03. No nuisance draw depends on the
  condition.

### T-026 — Within-episode instrument stability (unit)
- **Procedure.** Run 100 episodes, each with 6 accepted single-replicate requests at
  varied $(t, d)$. Recompute every audited noise-free reading from the episode's
  `AssayConfig`. Hash the `EpisodeConfig` before and after the episode.
- **Acceptance.**
  - All recomputed readings match the audit.
  - $S$ (and every assay parameter) is identical for every measurement of an
    episode.
  - The config hash is unchanged.

### T-027 — Visible late window (unit)
- **Procedure.** Take two `EpisodeConfig`s with very different hidden parameters
  ($t_{95}$ = 3.6 h vs 9.9 h) and evaluate lateness for requests at $t = 0..18$.
- **Acceptance.**
  - `is_late` is identical for both configs and equals $t \in [12, 18]$.
  - The lateness function takes only the requested time and the prior's
    `late_window_h`; it has no access to $K$, $S$, $r$, $X_0$ or $t_{95}$.

### T-028 — Scored prompt does not scaffold competing hypotheses (integration)
- **Procedure.** Render the scored system prompt, the tool definitions and the
  initial user message.
- **Acceptance.**
  - The system prompt and initial message are byte-identical to the committed
    `prompt-v1` snapshot.
  - Neither contains (case-insensitive) `hypothes`, `alternative`, `competing` or
    `explanation`, nor any instruction to call `declare_state`.
  - The `declare_state` description says it is optional.
  - No tool description contains the T-012 forbidden terms.
  - Any change to these surfaces fails this test until `prompt_version` is bumped
    and the snapshot updated with science-lead approval.

### T-029 — Gate 0 summary integrity (integration)
- **Procedure.** Run `scripts/gate0.py --quick` into a temporary directory and load
  `summary.json`.
- **Acceptance.**
  - Every key of GATE0_SPEC §7 is present: parameters, nuisance distributions,
    seeds, checks G0-A to G0-G (each with value, threshold, threshold type,
    blocking flag and pass flag), passive baseline, diagnostic dilution,
    `GoodScientist`, plots, scenario hash, source commit, versions.
  - `passed` equals the AND of the blocking checks.
  - Quick mode is marked so that it cannot be mistaken for a full pass.

### T-030 — Gate 0 plot generation (integration)
- **Procedure.** As T-029.
- **Acceptance.** `assay_response.png`, `passive_overlap.png`, `latent_reveal.png`,
  `intervention_sweep.png`, `separability_before_after.png` and `robustness_map.png`
  all exist, are non-empty valid PNGs, and are listed in `summary.json` `plots`.

### T-031 — Changed scientific configuration invalidates Gate 0 results (integration)
- **Procedure.** Copy `scenario_v1.json` and change one scientific parameter
  (e.g. $\kappa$ upper bound 0.90 → 0.91). Attempt a runner start against the
  original Gate 0 `summary.json`.
- **Acceptance.**
  - The canonical SHA-256 differs.
  - The runner refuses to start with a hash-mismatch error.
  - Formatting-only changes (key order, whitespace) do not change the hash.

## 4. Gate 0 ↔ test mapping

| Gate 0 check | pytest counterpart(s) | Difference |
|---|---|---|
| G0-A | T-008 | Gate 0 uses 1,000 test episodes per condition, 200,000 reference histories and 400,000 ceiling draws |
| G0-B | T-004, T-009 | Gate 0 uses 1,000 episodes |
| G0-C | T-005, T-010, T-015 | Gate 0 uses 1,000 episodes per condition |
| G0-D | none (Gate 0 only). D1/D2 blocking, D3 non-blocking | — |
| G0-E | T-019 | same size |
| G0-F | T-024, T-025, T-026 | Gate 0 uses 10,000 seeds per condition |
| G0-G | none (Gate 0 only; non-blocking) | — |
| Outputs and summary | T-029, T-030 | pytest uses `--quick` |

## 5. Requirement traceability (summary)

| Requirement | Tests |
|---|---|
| FR-001 to FR-005 | T-002, T-003, T-005, T-006, T-007, T-024 |
| FR-006, FR-007 | T-001, T-011 |
| FR-008, FR-009 | T-013, T-020 |
| FR-010 to FR-012 | T-020, T-022 |
| FR-013 to FR-015 | T-014, T-017, T-023 |
| FR-016 | T-018 |
| FR-017 | T-029, T-030 (+ full Gate 0 run, MS0 DoD) |
| FR-019 | T-028 |
| FR-018 | T-015, T-016 |
| NFR-001, NFR-002 | T-001, T-017, T-023 |
| NFR-005, NFR-006 | T-012, T-018 |
| SVR-001 | T-008 (+ G0-A) |
| SVR-002 | T-010, T-015 (+ G0-C) |
| SVR-003 | T-004, T-009 (+ G0-B) |
| SVR-004, SVR-005 | T-012 |
| SVR-006 | T-024, T-025, T-026 (+ G0-F) |
| SVR-007 | T-005, T-021, T-027 |
| SVR-008 | G0-D3 |
| SVR-009 | G0-D1, G0-D2 |
| SVR-010 | G0-G |
| ER-005, ER-007 | T-031 |

## 6. Planned test files

```text
tests/
├── conftest.py                 # shared fixtures: prior, demo pair, seeded configs
├── fixtures/
│   └── sample_episode_llm.json # small committed LLM-style record (for T-018)
├── test_growth.py              # T-002, T-003
├── test_assay.py               # T-006, T-007
├── test_config.py              # T-001, T-024
├── test_science.py             # T-004, T-005, T-008, T-009, T-010, T-019, T-025  (marker: science)
├── test_environment.py         # T-011, T-013, T-020, T-026
├── test_metrics.py             # T-014, T-021, T-023, T-027
├── test_runner.py              # T-015, T-016, T-017, T-031
├── test_gate0.py               # T-029, T-030 (gate0 --quick)
├── test_trust_boundary.py      # T-012, T-028
├── test_claude_adapter.py      # T-022
└── test_replay.py              # T-018
```
