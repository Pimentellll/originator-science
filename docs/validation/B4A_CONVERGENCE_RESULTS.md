# B4A: measured posterior convergence results

**Verdict: the declared convergence gate is NOT MET** by either the legacy engine or the adaptive-tempering engine, at
any tested particle count. This document reports the measurement. It does not relax the gate (which was declared before
any remedy was evaluated, in [POSTERIOR_CONVERGENCE_GATE.md](POSTERIOR_CONVERGENCE_GATE.md)) and no pass is claimed.

## Background

Baseline V1 used one-shot importance reweighting followed by resampling (SIR) with resample-move. Spot checks showed the
same evidence gave different posteriors at 512 vs 2048 particles. Diagnosis: sharp evidence relative to the belief makes
the weights collapse onto a few particles, so the causal marginals depend on which ancestors survive (particle
degeneracy), and the failure marginals that drive terminal decisions become unstable. Commit `97ac554` (a pushed commit
whose message is uninformative and is intentionally not rewritten) implements **adaptive-tempering SMC**: each
observation enters as `p(y|z)^τ`, τ 0→1, with every increment chosen to keep ESS ≥ 0.5 N, resampling and MCMC moves
between increments.

## Gate (declared in advance)

For production particle count N and reference 4N, 16 independent particle seeds, on fixed public traces (7-assay panel on
5 scenarios × 3 seeds, plus Baseline V1 invalid-model traces), at every trace prefix:

1. seed standard deviation of each of the eight marginals ≤ 0.05;
2. |mean(N) − mean(4N)| ≤ 0.05 per marginal;
3. Jensen-Shannon divergence between seed-mean joint failure-pattern distributions at N and 4N ≤ 0.02;
4. each marginal within 0.05 of a high-ESS importance-sampling reference where one exists.

If no N passes, the engine, not the tolerance, is changed.

## Measured (216 trace prefixes; raw output: [`convergence_audit.json`](convergence_audit.json))

Produced by `scripts/belief_convergence_audit.py` (16 seeds; commit `34fab90` on `feat/mirage-belief-eig`). "Failing"
means a prefix violating at least one gate criterion.

| Engine | N | Failing prefixes | Worst seed SD | Worst \|mean(N)−mean(4N)\| | Worst JSD vs 4N | Worst diff vs exact | Min mean weighted ESS frac | Replay s |
|---|---|---|---|---|---|---|---|---|
| legacy SIR | 256 | 204/216 | 0.493 | 0.577 | 0.290 | 0.304 | 0.005 | 0.2 |
| legacy SIR | 512 | 158/216 | 0.456 | 0.387 | 0.216 | 0.260 | 0.002 | 0.4 |
| legacy SIR | 1024 | 125/216 | 0.365 | 0.190 | 0.071 | 0.165 | 0.002 | 0.9 |
| legacy SIR | 2048 | 99/216 | 0.301 | n/a | n/a | 0.132 | 0.001 | 1.9 |
| legacy SIR | 4096 | 76/216 | 0.173 | n/a | n/a | 0.091 | 0.001 | 3.9 |
| **tempered** | 256 | 109/216 | 0.099 | 0.051 | 0.009 | 0.063 | 0.603 | 0.5 |
| **tempered** | 512 | 16/216 | 0.068 | 0.025 | 0.006 | 0.059 | 0.563 | 1.0 |
| **tempered** | 1024 | 1/216 | 0.040 | 0.023 | 0.003 | 0.075 | 0.529 | 2.0 |
| **tempered** | 2048 | 1/216 | 0.031 | n/a | n/a | 0.053 | 0.526 | 4.0 |
| **tempered** | 4096 | 1/216 | 0.020 | n/a | n/a | 0.052 | 0.519 | 7.6 |

("n/a": no 4N reference was run for N ≥ 2048.)

## Interpretation (what is and is not established)

- Adaptive tempering is a large improvement over legacy SIR: seed SD at 512 particles falls from 0.456 to 0.068 in the
  worst case, and the minimum weighted-ESS fraction rises from about 0.002 to about 0.56.
- It still **fails the gate at every N**. At N = 256 and 512 many prefixes fail (109 and 16). From N = 1024 one prefix
  fails on criterion 4 (agreement with the exact reference): 0.075 at N = 1024, and 0.053 / 0.052 at 2048 / 4096, which
  exceed the 0.05 tolerance by 0.002-0.003. The exact references themselves carry Monte Carlo error of about 0.02 at ESS
  300-900, so the residual at N ≥ 2048 is plausibly reference noise, but the gate was not changed after the fact and
  therefore is not met.
- The cost grows roughly linearly with N (1.0 s per trace replay at 512, 7.6 s at 4096).
- No "production particle count" has been selected under the gate. The live demo and RL use 256; the benchmark used 512.
- The audit tests whether the *engine* converges to the posterior of its own model. It says nothing about whether that
  model matches the environment (a known mismatch exists for degraded SPR; see
  [BINDER_ENVIRONMENT](../scientific-spec/BINDER_ENVIRONMENT.md#known-simulator-limits)).

## Tests

`tests/belief/test_belief_convergence_gate.py` encodes the gate against fixtures. At freeze, 2 of its tests fail:
`test_tempered_posterior_matches_exact_reference_at_512_particles` for `invalid_biological_model-50000-greedy_eig|1` and
`broken_assay-50000-greedy_eig|1` (the two share the same first-observation trace and reference): seed SD 0.0542 against
the 0.05 limit. These are the same failures present on `feat/mirage-belief-eig` itself; they are the unmet gate, not an
integration regression.

## Notes on provenance

- `docs/validation/POSTERIOR_CONVERGENCE_GATE.md` names a fixture `v1_invalid_model_traces.json`; the committed fixture is
  `tests/fixtures/belief_traces/v1_public_traces.json`. The gate document is a frozen declaration and was not edited.
- Commit `bb5ba96` on `feat/mirage-eval-api` ("record B4A adaptive-tempering posterior validation milestone") is an empty
  commit (no files). It is not part of the integration branch's content and should not be read as a passed validation.
- The convergence audit output was committed as `34fab90` on `feat/mirage-belief-eig` and cherry-picked onto
  `feat/mirage-integration`.

## Status

Validation remains **in progress**. Open work: choose an engine/particle count that meets the gate, or amend the
declared gate with a documented new version before looking at any policy score; then rerun policies on the converged
engine.
