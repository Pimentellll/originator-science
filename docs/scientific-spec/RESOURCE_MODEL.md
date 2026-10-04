# Resource model

`ResourceState` is public and separate from molecular truth: non-negative `budget_remaining`, `sample_remaining`,
`simulated_time`, and `spr_instrument_health` in [0, 1], plus the public candidate lineage.

Defaults at reset: budget 12.0, sample 8.0, time 0.0, SPR health 1.0. Every measurement, validation or redesign action
charges its configured budget, sample and time (see [ACTION_OBSERVATION_CONTRACT](ACTION_OBSERVATION_CONTRACT.md)). An
experiment is simply not in `available_actions()` when budget or sample cannot cover it; terminal actions stay available.
Accounting is rounded to 8 decimals.

**Path dependence is mandatory.** SPR on a severely aggregated sample (`monomer_fraction < 0.45`), or on an instrument
already below health 0.70, returns a degraded reading and reduces SPR health by 0.28. A damaged instrument keeps
returning degraded readings regardless of the molecule. Sample depletion, budget depletion, elapsed time, redesign and
instrument health therefore create campaign-level trade-offs: the order SEC → solubility redesign → SPR can preserve
kinetic evidence that SPR-first destroys.

Time only accumulates. There is no deadline, so time is neither binding nor observable; the V2 preregistration records
that it does not randomise time for this reason.

The Binder Rescue V2 preregistration varies only the *initial* resources (LOW/MEDIUM/HIGH strata); see
[BINDER_RESCUE_V2](../evaluation/BINDER_RESCUE_V2.md).
