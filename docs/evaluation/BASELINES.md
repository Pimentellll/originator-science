# Baselines

RandomPolicy, FixedPipelinePolicy, and GreedyEIGPolicy are MVP baselines under one ScientificPolicy contract. Greedy EIG is myopic and estimates one-step entropy reduction; it may be cost-aware but does not plan future instrument preservation unless extended.

PPOPolicy is compared through the same public interface and seed matrix. On genuinely myopic worlds Greedy EIG should remain competitive. MIRAGE must not claim RL wins by default or report fabricated benchmark results.
