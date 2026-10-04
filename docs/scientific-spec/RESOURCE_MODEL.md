# Resource model

ResourceState is public and separate from molecular truth. It includes nonnegative budget, sample remaining, simulated time, and SPR instrument health in [0,1], plus public candidate lineage context.

Every measurement/validation action charges configured budget, sample where relevant, and time. Insufficient resources make an action unavailable or return a public invalid-action outcome without a hidden-state leak. Redesign consumes configured resources and produces a new candidate generation.

Path dependence is mandatory. Premature SPR on a severely aggregated sample can both reduce observation quality and decrease future SPR health. Sample depletion, budget depletion, elapsed time, redesign, and instrument state create campaign-level trade-offs.
