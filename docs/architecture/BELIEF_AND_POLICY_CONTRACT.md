# Belief and policy contract

## Belief

The MVP is a particle-based Bayesian belief over factorised latent states. Start with particles z_i and weights 1/N. After public observation y from action a, update log weights by log p(y | z_i, a), normalise, compute ESS, and resample when configured threshold requires it. Default particle count near 512 is configurable, not a scientific constant.

Public BeliefSummary reports non-exclusive probabilities for folding, aggregation, affinity, kinetic, epitope, developability, assay-invalid, and model-invalid mechanisms, plus posterior entropy, relevant means/variances, and ESS. It must not expose particle identities or truth.

## Policy

A common ScientificPolicy accepts only AgentState, BeliefSummary, available public actions, and an optional seeded policy RNG; it returns ScientificAction. RandomPolicy, FixedPipelinePolicy, GreedyEIGPolicy, PPOPolicy, and optional ClaudeScientistPolicy use this same contract. Greedy EIG estimates H(b_t) - E[H(b_t+1)] and is explicitly myopic. Policies cannot self-score scientific success.
