# MIRAGE analysis and design

## Requirements analysis

MIRAGE evaluates active causal reasoning under ambiguity. A policy must observe noisy evidence, maintain uncertainty over multiple mechanisms, choose discriminating experiments under cost and path dependence, and make a bounded terminal claim. Correctness alone is insufficient: independent evaluation checks whether the recorded evidence supports the claim.

## Current-system analysis

The repository already contains a working growth/OD regression benchmark, virtual lab, deterministic evaluator, scripted baselines, Claude adapter, runner, records, replay, and pytest suite. It is not an empty scaffold. That benchmark is preserved as the original MIRAGE environment and regression target.

## Scientific problem analysis

A failing de novo binder may be unstable, aggregated, weakly binding, fast-dissociating, directed to a non-functional epitope, developability-limited, measured by a broken assay, or evaluated through an invalid biological model. Several can co-occur. Passive functional failure is therefore deliberately insufficient evidence.

## Architectures considered

A single mutually exclusive failure label is rejected because it cannot represent compound failure. A deterministic pass/fail assay table is rejected because it makes inference trivial. A sequence-generating RL action space is rejected because MIRAGE evaluates campaign decisions, not amino-acid generation. A single reward as evaluator is rejected because it conflates training optimization with scientific justification.

## Selected architecture

BinderBioPOMDP owns a private, factorised causal state and emits overlapping stochastic observations. A particle belief approximates posterior uncertainty. Common policies choose canonical ScientificAction values. Resources and instrument health form a separate state component. Redesign produces a new lineage member through explicitly synthetic simulator transitions. A privileged evaluator scores correctness and justification independently.

## Component and data design

Public contracts contain actions, lineage metadata, resource state, observations, state snapshots, and public provenance. They reject extra fields. Private truth includes stability, monomer fraction, log KD, log koff, functional epitope, developability liability, assay validity, and model validity. Environment-to-policy flow is one-way through public observations.

## Planning design

Greedy EIG is intentionally myopic and should be competitive on myopic worlds. Path-dependent worlds expose its limitation: sending an aggregated sample to SPR may harm the instrument and reduce later kinetic evidence. Campaign-level planners can favour SEC, repair, then SPR. PPO is an MVP planner, not a claim of definitive scientific planning.

## Evaluation and frontend design

Evaluation consumes a public trace plus privileged truth. It separates correct from justified and reports cost, compound recognition, invalid-assay/model detection, and proxy exploitation. The Scientific Cockpit shows candidates, evidence, belief, resources, recommendations, timeline/replay, policy comparison, and benchmark lab. It never receives truth.

## Risks, migration, testing, demo

Risks include leakage, non-identifying assay models, reward hacking, misleading biological claims, and incompatible workstreams. Add new packages alongside the existing benchmark; do not broadly refactor it. Test determinism, leak-free JSON, every action, resource transitions, posterior response, same-seed policy comparison, replay, and correct-versus-justified outcomes. Demonstrate a seeded case where myopic SPR is attractive but SEC-first preserves future capability.

## Claim boundaries and future extensions

MIRAGE is a synthetic, biologically grounded benchmark, not a digital twin, therapeutic discovery system, clinical predictor, wet-lab replacement, or exact physical simulator. Future design engines may include ProteinMPNN, FoldX, RFdiffusion, Bayesian optimisation, and active learning, but are outside the MVP.
