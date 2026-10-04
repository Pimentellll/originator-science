# Belief and policy contract

Checked against `d182a2c`.

## Public observation

`ScientificObservation` is a public structured result:

```text
action_type: ActionType
candidate_id: str
measurements: dict[str, float]   # named assay outputs, finite floats
quality: str                     # "nominal" or "degraded" in the Binder environment
notes: tuple[str, ...]           # each 1-256 characters
```

Measurements are named numeric quantities, never one overloaded scalar and never arbitrary metadata. SEC exposes
`monomer_fraction`; SPR exposes `log_kd` and `log_koff`. Names are assay outputs; they do not make the corresponding
private latent values visible.

## Latent schema and failure marginals

A particle is one plausible factorised world, a row over eight factors (`mirage.belief.schema`):

`stability`, `monomer_fraction`, `log_kd`, `log_koff`, `functional_epitope`, `developability_liability`,
`assay_valid`, `model_valid` (the three booleans are stored as 0.0/1.0).

`BeliefSummary` exposes eight **non-exclusive** failure marginals, each the posterior mass of a threshold rule:

| Marginal | Rule in `BINDER_SCHEMA_PROVISIONAL` | Rule in the benchmark's `LabelRules` (`campaign-eval/1`) |
|---|---|---|
| `p_folding_failure` | stability < 0.6 | stability < 0.5 |
| `p_aggregation_failure` | monomer_fraction < 0.6 | monomer_fraction < 0.6 |
| `p_affinity_failure` | log_kd > -7.0 | log_kd > -7.0 |
| `p_kinetic_failure` | log_koff > -2.0 | log_koff > -2.0 |
| `p_epitope_failure` | functional_epitope = 0 | functional_epitope = 0 |
| `p_developability_failure` | liability > 0.4 | liability > 0.4 |
| `p_assay_invalid` | assay_valid = 0 | assay_valid = 0 |
| `p_model_invalid` | model_valid = 0 | model_valid = 0 |

Also: `posterior_entropy` (sum of the eight binary entropies, nats, in [0, 8 ln 2]), `continuous_means`,
`continuous_variances`, `effective_sample_size`. The marginals do not sum to one. `BeliefSummary` never exposes
particles, particle identities or truth. The thresholds are **provisional benchmark-engineering parameters**; the
`LabelRules` variant is what Baseline V1 and the V2 preregistration use, and it differs from the environment's own
`evaluator_truth` labels (see [BINDER_ENVIRONMENT](../scientific-spec/BINDER_ENVIRONMENT.md#label-rule-inconsistency)).

## Inference: `ParticleBelief`

| Property | Value |
|---|---|
| Particles | seeded draws from a public prior; 512 in the benchmark, 256 in the live controller and the RL stack |
| Likelihood | `BinderPredictiveModel.log_likelihood`: independent Gaussians, σ = 0.08 nominal, 0.18 for a "degraded" reading; a quality or measurement-name mismatch gives -inf |
| Default update | **adaptive-tempering SMC** (`tempering=True`, commit `97ac554`) |
| Resampling | systematic (stratified available) when ESS falls below `ess_threshold` × N (default 0.5) |
| Rejuvenation | resample-move: Metropolis-within-Gibbs sweeps per factor (binary factors flip with probability 1/2) that leave prior × evidence history invariant; needs a prior with a density and the full evidence history, so it is off after a redesign |
| Redesign | the belief about the new candidate is the parent cloud pushed through the public redesign kernel; the evidence history restarts |
| Degenerate evidence | `DegenerateBeliefError` if every particle has zero likelihood; the controller/RL trackers leave the belief unchanged and count the event |

**Adaptive tempering.** Each observation enters as `p(y|z)^τ` with τ rising 0 → 1. Every increment is the largest one
that keeps ESS ≥ `ess_threshold` × N (bisection); after each increment the particles are resampled and moved by MCMC
targeting prior × history × `p^τ`. The one-shot reweight-then-resample used by Baseline V1 is the single-stage
special case, and degenerates when the likelihood is sharp relative to the belief. Whether the tempered engine is
accurate enough is **an open question**: [B4A results](../validation/B4A_CONVERGENCE_RESULTS.md).

## Derived views (library only)

- `FailureLocalisation`: posterior mass on molecule / experiment / model failure (molecule is the *union* of the six
  molecular rules), the compound-molecule probability, an exhaustive locus joint over 8 locus combinations, and the
  leading locus.
- `JustificationCertificate`: the agent's own account of how justified a terminal would be now: top competing
  explanations (joint failure patterns), whether alternatives are still plausible, whether the assay control has been
  run and resolved, whether model failure is separable from assay failure, the top-EIG experiment, the recommended
  terminal with its probability of being correct, and what evidence is missing. It applies evidence gates (`SELECT`
  and `MODEL_INVALID` need assay integrity established; `ABSTAIN` needs a real diagnostic) and an optional posterior
  predictive check.
- Belief-side terminal semantics (`mirage.belief.decision`): any molecular failure → `REJECT`; good molecule and valid
  model → `SELECT`; good molecule, invalid model, valid assay → `MODEL_INVALID`; good molecule, invalid model, invalid
  assay → `ABSTAIN`.

These are the **scientist's own approximation** for planning and self-assessment. They are not the evaluator. They are
**not** produced by the controller or served by the API.

## Policy contract

```python
choose_action(state: AgentState, belief: BeliefSummary, available_actions: Sequence[ScientificAction]) -> ScientificAction
```

A policy receives only those three public inputs and must return one element of `available_actions`; it never receives
the environment or truth. `reset(seed)` restarts any internal stream. All of Random, FixedPipeline, GreedyEIG,
Lookahead, ReceptorRescuePlanner and PPOPolicy implement exactly this. GreedyEIG and Lookahead are constructed with a
`belief_source` callable returning the controller-held `ParticleBelief` (hypothetical particles only); the public
`BeliefSummary` is checked against it for consistency.

| Policy | Closing rule |
|---|---|
| Random, FixedPipeline, GreedyEIG, ReceptorRescuePlanner | shared `threshold_terminal_decision` at 0.5: any molecular marginal ≥ t → `REJECT`; else `p_assay_invalid` ≥ t → `ABSTAIN`; else `p_model_invalid` ≥ t → `MODEL_INVALID`; else `SELECT` |
| Lookahead | expected terminal utility under its own (configurable) utilities with evidence gates; stops when no further assay or redesign beats stopping |
| PPO | a learned discrete action over the 14 actions, with an action mask |

Policies cannot self-score scientific success: training reward is not evidence (ADR 0006).
