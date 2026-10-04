# Assay models

Every assay maps private truth plus seeded noise to a public structured observation: named numeric measurements, quality, and optional public notes. Values are assay estimates, not copies of latent state. Exact numerical parameters are configurable modelling assumptions, not biological constants.

| Assay | Factors informed | Public fields and artifact behavior |
| --- | --- | --- |
| stability | folding/stability | stability_proxy; noisy readout |
| SEC | monomer fraction | monomer_fraction; aggregation evidence |
| SPR | affinity, kinetics, aggregation | log_kd, log_koff, quality; aggregated input can be unreliable and reduce future SPR health |
| epitope | functional epitope | epitope_signal; overlapping evidence |
| developability | liability | liability_proxy; noisy risk evidence |
| assay control | assay validity | control_signal; detects broken downstream assay |
| orthogonal function | assay/model separation | orthogonal_function_signal; distinguishes invalid assay from invalid model |

Assay likelihoods are shared with particle inference where feasible. They are versioned with the environment and tested for reproducibility, nontrivial overlap, path dependence, and no leakage.
