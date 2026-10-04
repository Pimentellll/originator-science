# Posterior convergence gate (declared before any policy ranking is looked at)

**Status:** frozen when committed. It is a property of the inference engine, evaluated on fixed public
evidence traces; it must never be tuned using policy scores.

## Why this gate

Failure marginals feed threshold decisions (the baselines close at 0.5; the planners compare expected
utilities). A marginal that moves by 0.05 can change a decision only when it lies within 0.05 of a
decision boundary, and a seed-to-seed standard deviation of 0.05 keeps the 2-sigma band at 0.10. Larger
errors make a policy's behaviour depend on its particle RNG seed rather than on evidence. 0.05 is also
about the Monte Carlo error of the exact importance-sampling reference used for the early prefixes
(ESS 300-900), so a tighter gate could not be verified.

## Evidence

* `tests/fixtures/belief_traces/public_traces.json`: the 7-assay panel on 5 canonical scenarios x 3 seeds
  (public actions and observations only), evaluated at every prefix k = 1..7.
* `tests/fixtures/belief_traces/v1_invalid_model_traces.json`: cited in the original gate design but never
  committed to the repository.
* Agent-side prior and label rules: exactly those recorded in the Baseline V1 manifest
  (`campaign-eval/1`), because that is the configuration whose behaviour was questioned.

## Gate (all must hold, for every trace prefix)

For production particle count `N` and reference `N_ref = 4 * N`, with 16 independent particle-RNG seeds each:

1. **Seed stability:** for each of the 8 failure marginals, standard deviation across seeds at `N` <= 0.05.
2. **Agreement with a larger run:** for each marginal, |mean_seed p(N) - mean_seed p(N_ref)| <= 0.05.
3. **Distributional agreement:** Jensen-Shannon divergence (nats, bounded by ln 2) between the seed-mean
   joint failure-pattern distributions at `N` and `N_ref` <= 0.02.
4. **Accuracy where an exact reference exists:** for prefixes whose posterior can be computed by
   high-ESS importance sampling, each marginal within 0.05 of that reference.

The production particle count is the smallest `N` in {256, 512, 1024, 2048} that passes on every trace.
If none passes, the engine, not the tolerance, is changed.
