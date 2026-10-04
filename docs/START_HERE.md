# MIRAGE: start here

MIRAGE is an autonomous causal experimental-planning system for diagnosing and rescuing failed de novo
miniprotein binder campaigns: a **synthetic, semi-mechanistic benchmark and decision architecture** for testing
whether autonomous scientific agents can diagnose a failed binder campaign, choose informative experiments under
resource constraints, and reach conclusions the experiments actually justify.

The central idea is **CORRECT ≠ JUSTIFIED**. An agent can reach the correct terminal decision for the wrong reason,
so a privileged evaluator scores *correct* and *justified* separately. Read the [root README](../README.md) first;
it is the 5-minute version of everything below.

Every statement in these documents was checked against the implementation freeze
`d182a2ce5340fd3e12804b3643ee90e9e080d788` on `feat/mirage-integration`.

## Status at the freeze

| Area | Status |
|---|---|
| Binder BioPOMDP (14 public actions, factorised private truth, redesign, SPR path dependence) | IMPLEMENTED |
| Scenario semantics: `BASELINE_V1` (default, frozen) and `SEMANTICS_V2` (A5) | IMPLEMENTED |
| Particle belief with adaptive-tempering SMC, EIG, FailureLocalisation, JustificationCertificate | IMPLEMENTED; **posterior convergence gate (B4A) NOT MET** |
| Policies: Random, FixedPipeline, GreedyEIG, ReceptorRescuePlanner, Lookahead | IMPLEMENTED |
| Privileged evaluator (correct vs justified), harness, aggregates, adversarial suite | IMPLEMENTED |
| Provenance, JSONL store, model-free replay, leakage scanner | IMPLEMENTED |
| Public FastAPI layer (DTO boundary) | IMPLEMENTED; serves `random`, `fixed_pipeline`, `rescue_planner` |
| Scientific Cockpit (E1, live transport) | IMPLEMENTED |
| Gym wrapper, reward, MaskablePPO training, `PPOPolicy` adapter | IMPLEMENTED; **no valid checkpoint, PPO NOT RUN** |
| Baseline V1 (Random / FixedPipeline / GreedyEIG, 250 worlds) | DONE, frozen, immutable |
| Lookahead evaluation | **NOT RUN** |
| Binder Rescue V2 | PREREGISTERED and locked; **no runner, no results; lock fails verification on this branch** |
| Modal / cloud training | NOT IMPLEMENTED (training is local, `python -m mirage.rl.train`) |
| Legacy MIRAGE-Bio growth benchmark | IMPLEMENTED, retained, separate |

## Reading order

1. [Root README](../README.md): what it is, why it is hard, correct ≠ justified, how to run.
2. [MIRAGE.md](MIRAGE.md): the framing and the failure hierarchy.
3. Architecture: [overview](architecture/MIRAGE_ARCHITECTURE.md) · [system context](architecture/SYSTEM_CONTEXT.md) ·
   [trust boundary](architecture/TRUST_BOUNDARY.md) · [belief and policy contract](architecture/BELIEF_AND_POLICY_CONTRACT.md) ·
   [provenance and replay](architecture/PROVENANCE_AND_REPLAY.md) · [frontend/API contract](architecture/FRONTEND_API_CONTRACT.md) ·
   [analysis and design](architecture/ANALYSIS_AND_DESIGN.md).
4. Scientific specification: [Binder environment](scientific-spec/BINDER_ENVIRONMENT.md) ·
   [causal state](scientific-spec/CAUSAL_STATE.md) · [actions and observations](scientific-spec/ACTION_OBSERVATION_CONTRACT.md) ·
   [assay models](scientific-spec/ASSAY_MODELS.md) · [resources](scientific-spec/RESOURCE_MODEL.md) ·
   [redesign](scientific-spec/REDESIGN_MODEL.md) · [scenario generation](scientific-spec/SCENARIO_GENERATION.md).
5. Evaluation: [policy taxonomy](evaluation/BASELINES.md) · [metrics and evidence rules](evaluation/METRICS.md) ·
   [protocol](evaluation/BENCHMARK_PROTOCOL.md) · [reward hacking](evaluation/REWARD_HACKING_SUITE.md) ·
   [Baseline V1 analysis](evaluation/BASELINE_V1.md) · [V2 preregistration (locked)](evaluation/BINDER_RESCUE_V2.md) ·
   [V2 status](evaluation/BINDER_RESCUE_V2_STATUS.md).
6. Validation: [B4A convergence gate](validation/POSTERIOR_CONVERGENCE_GATE.md) and its
   [measured results](validation/B4A_CONVERGENCE_RESULTS.md).
7. Implementation: [acceptance gates](implementation/ACCEPTANCE_GATES.md) · [work packages](implementation/WORK_PACKAGES.md) ·
   [migration](implementation/MIGRATION_PLAN.md) · [execution plan (historical)](implementation/SIX_HOUR_EXECUTION_PLAN.md).
8. Decisions: [ADRs](adr/) 0001-0011.
9. Frontend: [frontend/README.md](../frontend/README.md).
10. Research context (not implemented): [research/](research/README.md).

## Contract precedence

The documents under `architecture/`, `scientific-spec/`, `evaluation/` and `implementation/` describe the Binder
system and win over `mirage-bio/` wherever they overlap. `docs/mirage-bio/` is the historical record of the
earlier growth benchmark and is authoritative only for that benchmark. The V2 preregistration
(`evaluation/BINDER_RESCUE_V2.md`) and the Baseline V1 results are **frozen records**: they are never edited, only
supplemented by new documents.

Synthetic parameters and assay behaviour are MIRAGE design choices, not biological claims.
