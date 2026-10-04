# Action and observation contract

Canonical names are frozen (`mirage.core.ActionType`). Public observations use `action_type`, `candidate_id`,
`measurements: dict[str, float]`, `quality` and optional public `notes`. Arbitrary generic metadata is forbidden because
it would be a truth-leak channel.

Costs are the environment's configured values (`_COSTS` in `environments/binder/environment.py`); they are pinned by
tests in the policy and V2 code that reuse them.

| Action | Public measurements | Budget | Sample | Time | Notes |
|---|---|---|---|---|---|
| `MEASURE_STABILITY` | `stability_proxy` | 1.0 | 0.5 | 0.5 | folding evidence |
| `MEASURE_SEC` | `monomer_fraction` | 1.0 | 0.5 | 0.5 | aggregation evidence; run before SPR |
| `MEASURE_SPR` | `log_kd`, `log_koff` | 2.0 | 1.0 | 1.0 | degraded on aggregated samples or a degraded instrument; damages SPR health (0.28 per degraded read) |
| `MEASURE_EPITOPE` | `epitope_signal` | 1.0 | 0.4 | 0.5 | functional-epitope evidence |
| `MEASURE_DEVELOPABILITY` | `liability_proxy` | 1.0 | 0.4 | 0.5 | developability evidence |
| `VALIDATE_ASSAY` | `control_signal` | 0.75 | 0.1 | 0.25 | assay-integrity control |
| `ORTHOGONAL_FUNCTION` | `orthogonal_function_signal` | 1.5 | 0.25 | 0.75 | separates assay from model explanations |
| `REDESIGN_STABILITY` | none; new candidate | 2.0 | 1.0 | 1.0 | expected stability gain, weak trade-offs |
| `REDESIGN_SOLUBILITY` | none; new candidate | 2.0 | 1.0 | 1.0 | expected aggregation gain |
| `REDESIGN_INTERFACE` | none; new candidate | 2.0 | 1.0 | 1.0 | expected affinity/kinetic gain, small stability cost |
| `SELECT` `REJECT` `MODEL_INVALID` `ABSTAIN` | none | 0 | 0 | 0 | terminal; ends the episode |

Running all seven assays once costs 8.25 budget, 3.15 sample and 4.0 time.

Observation distributions overlap across mechanisms. A measurement name describes an assay readout, not a truth field;
no action returns a perfect latent factor or a trivial healthy/failure code. Preconditions: the episode is not terminal,
the candidate exists, and budget and sample cover the cost (terminal actions are always available). An action not in
`available_actions()` is rejected with `ValueError`.
