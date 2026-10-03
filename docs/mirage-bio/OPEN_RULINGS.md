# Open science rulings (for Arnav)

This is not a specification. It collects every "Needs ruling" item from the merged
implementation PRs, as of `wip/integration` at `d37497b`. Provisional decisions are
recorded at the end (§F); none of them changed any code. For each item, the current behaviour is stated, and the code keeps that
behaviour until a ruling is made. The numbers come from the committed candidate Gate 0
run `experiments/results/gate0/summary.json` (#40, source `a05155e`, full mode,
`passed: true`) or from recomputation with `mirage.assay.od_reader.t_q`.

## A. Blocks freezing Gate 0

**1. G0-C(iv): sampled maximum or support supremum** (#3, #30, #31, #40)
- **Spec.** GATE0_SPEC §4 requires $t_{95} + 2\,\text{h} \le 12$ h in 100 % of 10,000
  scenarios per condition.
- **Candidate run.** The sampled maximum is 11.858 h, so the check passes.
- **Support corner.** The slowest corner of the scenario-v1 support is $K = 10$, $S = 2$,
  $r = 0.6$, $X_0 = 0.005$, $n = \nu = 8$. It gives $t_{95} = 10.127$ h, so
  $t_{95} + 2 = 12.127$ h, above the 12 h limit. The corner is pinned by the strict xfail
  `tests/test_assay.py::test_t005_window_validity_at_support_corner`.
- **Code.** `scripts/gate0.py::g0c_iv_passes` implements the check exactly as written.
  Any ruling changes one line there.
- **Options.** #40 refers to an A/B/C list that I could not find in the repo or the
  issues. The options as I understand them:
  - (a) Keep the check sampled, as written, and record the corner in RISKS.md. The
    candidate run can then be frozen. #40 recommends this.
  - (b) Require the bound over the whole support. Gate 0 would then fail until the
    prior or the late window changes.
  - (c) Change the prior or the late window. This changes the scenario-v1 hash, so
    Gate 0 must be re-run.

## B. Needed before any scored Claude run

**2. Matrix condition assignment** (#33)
- EXPERIMENT_PLAN gives "10 (5 BP, 5 MA)" but doesn't say which seed gets which
  condition.
- `eval_matrix_v1.json` alternates by seed parity: even seeds are
  `BIOLOGICAL_PLATEAU`, odd seeds are `MEASUREMENT_ARTIFACT`.
- Please confirm or replace.

**3. Approve the prompt-v1 snapshot** (#35)
- `tests/snapshots/prompt_v1.json` was generated from the frozen visible interface, not
  written by hand.
- DEV-013 freezes the prompt, and approving the snapshot is what makes it the
  committed one.

**4. ITT M2 for API_FAILURE / REFUSED** (#38)
- ITT currently sets `diagnostic_control = False` and `justified = False` for these
  episodes.
- On the hand-built fixture this gives ITT M2 = 2/5. Keeping the control derived from
  the measurements would give 3/5.
- DESIGN §15 only says ITT counts these episodes as incorrect.
- The current behaviour is pinned by `test_itt_clears_control_for_api_failure_and_refused_pinned`.

**5. T-016 agreement with G0-A** (#32)
- TEST_PLAN T-016 requires balanced M1 within ±0.05 of the G0-A `PassiveBayes` value
  "where available". The candidate value is 0.567.
- Should this be checked in the scripted-agent tests, or only in the runner once Gate 0
  is frozen?

## C. Record schema (needs `episode-result-v2` if changed)

**6. Store failed clauses** (#38)
- DESIGN §15 says the audit stores every failed M2 and Q1 clause.
- `MeasurementAudit` in `episode-result-v1` has no field for them, so
  `metrics.failed_clauses()` computes them on demand.
- Storing them is a schema change.

**7. No events after an accepted diagnosis** (#38)
- The record validator rejects events after an accepted diagnosis, because
  `LabEnvironment` raises on any call after `finish`.
- Should this be relaxed if a future runner logs events after the diagnosis?

## D. Config validation policy (DESIGN §13 is silent) (#37)

8. **`passive_times_h`.** Only "non-empty" is enforced. Must it equal `0..max_time_h`?
   `LabEnvironment` ignores this field.
9. **`plateau_fraction`.** Only "finite" is enforced. Must it be in (0, 1)?
10. **`kappa_uniform` / `lambda_uniform` positivity, and `late_window_h` ⊂ [0, `max_time_h`].**
    Only `lo < hi` and finiteness are enforced.

## E. Confirm the current reading (no change expected)

11. **Diagnostic set.** The candidate D_diag is `[1.1, 100]` with 1 replicate: every
    grid dilution except $d = 1$ is diagnostic. M2 therefore credits any late,
    pre-diagnosis dilution in that range.
12. **G0-G robustness.** The `n=7` variant has a maximum BP compression of 5.43 %, above
    the 5 % limit. G0-G is non-blocking, and GATE0_SPEC already lists this as a
    documented boundary.
13. **Gate 0 figures** (#31)
    - The optional `intervention_sweep` panel (d) is omitted.
    - `separability_before_after` plots AUROC discriminability
      $\max(a, 1-a)$, not balanced accuracy, and the axis label says so.
14. **T-002.** TEST_PLAN asks for "strictly increasing" and $X < K$. In float64 the
    closed form reaches $K$ exactly once the remaining gap drops below one ulp. The test
    therefore asserts:
    - $X \le K$;
    - strictly increasing where $X < K(1 - 10^{-9})$;
    - non-decreasing overall.

## F. Provisional decisions (3 October 2026)

The science lead was unavailable. Ben (code owner) took the decisions below as
**provisional, pending Arnav**. Every one of them keeps the current behaviour, so no
code, threshold, schema or config changed. Arnav may overturn any of them. Overturning
item 1 means a new scenario version and a full Gate 0 re-run (GATE0_SPEC §8).

| # | Decision |
|---|---|
| 1 | Option (a). G0-C(iv) is the sampled check as written, and the support corner is recorded as RISKS R-027. Gate 0 is frozen (below). |
| 2 | Keep the seed-parity assignment: even seeds `BIOLOGICAL_PLATEAU`, odd seeds `MEASUREMENT_ARTIFACT`. |
| 3 | `tests/snapshots/prompt_v1.json` is approved as the frozen `prompt-v1`. |
| 4 | Keep ITT clearing `diagnostic_control` and `justified` for `API_FAILURE` / `REFUSED`. |
| 5 | Deferred. Doesn't block scored runs. |
| 6 | No schema change. Failed clauses stay computed on demand by `metrics.failed_clauses()`. |
| 7 | Keep rejecting events after an accepted diagnosis. |
| 8–10 | Keep the current validation. No extra restrictions. |
| 11–14 | The current reading is confirmed. |

**Gate 0 freeze.** The frozen artefacts are the committed full run in
`experiments/results/gate0/` (#40, `source_commit` `a05155e`, `scenario_sha256`
`5291e69c…c0ce08`). No Gate 0 input (`scripts/gate0.py`, `src/mirage/assay`,
`src/mirage/biology`, `src/mirage/config.py`, `experiments/configs/scenario_v1.json`)
has changed since `a05155e`. A full re-run on `main` at `4bcf15b` reproduced every
field of `summary.json` exactly, apart from `runtime_s`, `source_commit` and
`versions`. The strict xfail
`test_t005_window_validity_at_support_corner` stays in place: it documents R-027.
