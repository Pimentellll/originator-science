# Belief and policy contract

## Public observation and belief summary

ScientificObservation is a public structured result:

    action_type: ActionType
    candidate_id: str
    measurements: dict[str, float]
    quality: str
    notes: tuple[str, ...]

Measurements use named numeric quantities, not one overloaded scalar and not arbitrary metadata. For example, SEC may expose monomer_fraction and SPR may expose log_kd and log_koff estimates. Names are public assay outputs; they do not make the corresponding private latent values visible.

The MVP is a particle-based Bayesian belief over factorised latent states. Start with particles z_i and weights 1/N. After public observation y from action a, update log weights by log p(y | z_i, a), normalise, compute effective sample size, and resample when the configured threshold requires it. Default particle count near 512 is configurable, not a scientific constant.

BeliefSummary has these semantic fields:

    p_folding_failure
    p_aggregation_failure
    p_affinity_failure
    p_kinetic_failure
    p_epitope_failure
    p_developability_failure
    p_assay_invalid
    p_model_invalid
    posterior_entropy
    continuous_means: dict[str, float]
    continuous_variances: dict[str, float]
    effective_sample_size

The failure marginals are not mutually exclusive and do not sum to one. BeliefSummary must not expose particles, particle identities, or truth.

## Policy

The common public policy operation is equivalent to:

    choose_action(state, belief, available_actions) -> ScientificAction

It receives AgentState, BeliefSummary, and a sequence of currently available ScientificAction values only; it never receives the environment object or privileged truth. RandomPolicy, FixedPipelinePolicy, GreedyEIGPolicy, PPOPolicy, and optional ClaudeScientistPolicy use this same contract. Greedy EIG estimates one-step H(b_t) - E[H(b_t+1)] and is explicitly myopic. PPO is campaign-level and policies cannot self-score scientific success.

## Implementation alignment

The initial core contract at commit 306f055 exposes scalar observation value and uncertainty. Structured measurements are the frozen target contract; the core workstream must align its public model before Binder BioPOMDP integration.
