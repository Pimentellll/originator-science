# Assay models

Checked against `BinderPredictiveModel` (`environments/binder/predictive.py`) and `BinderBioPOMDP._measure`.

Every assay maps private truth plus seeded Gaussian noise to a public structured observation. Readings are assay
estimates, not copies of latent state. The belief engine uses the **same** public model as its likelihood, so this table
is also the belief's observation model.

| Assay | Public field(s) | Mean | Noise σ (nominal) |
|---|---|---|---|
| stability | `stability_proxy` | `stability` | 0.08 |
| SEC | `monomer_fraction` | `monomer_fraction` | 0.08 |
| SPR | `log_kd`, `log_koff` | `log_kd`, `log_koff` | 0.08 |
| epitope | `epitope_signal` | 0.82 if functional epitope else 0.24 | 0.08 |
| developability | `liability_proxy` | `developability_liability` | 0.08 |
| assay control | `control_signal` | 0.86 if assay valid else 0.23 | 0.08 |
| orthogonal function | `orthogonal_function_signal` | 0.80 if (functional epitope and assay valid) else 0.28 | 0.08 |

**SPR degradation.** If `monomer_fraction < 0.45` (or, in the environment only, SPR health < 0.70) the reading is
labelled `quality = "degraded"` with the note "SPR result quality degraded by sample behaviour.", costs the instrument
0.28 health (floored at 0) and is noisier and biased upward. The public model assumes bias +0.35 and σ 0.18. The
environment's degraded path adds a further +0.35 and uses σ = 0.18 + (1 − health) × 0.08, so the realised bias is
about +0.70 (see the simulator limits in [BINDER_ENVIRONMENT](BINDER_ENVIRONMENT.md#known-simulator-limits)).

Consequences by design:

- the epitope, control and orthogonal signals are bimodal and separate hypotheses well, but only at a noise of 0.08
  around two means about 0.5-0.6 apart; they are informative, not oracular;
- `model_valid` affects no assay directly. Model invalidity is supported by a valid control, direct or orthogonal target
  evidence, and a failing downstream expectation (evaluator rules in [METRICS](../evaluation/METRICS.md));
- proxies (stability, SEC, developability) never establish function on their own.

Assay likelihoods are versioned with the environment and tested for reproducibility, non-trivial overlap, path
dependence and the absence of leakage. All parameters are modelling assumptions.
