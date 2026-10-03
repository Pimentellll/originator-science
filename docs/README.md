# Documentation index

```text
MIRAGE                                  the project: epistemic evaluation of autonomous scientists
│
├── benchmark methodology / evaluation principles     (docs/*.md)
│
└── MIRAGE-Bio                          the first concrete environment  (docs/mirage-bio/)
```

**Specification status:**

| Item | Status |
|---|---|
| MIRAGE-level methodology | Documented |
| MIRAGE-Bio v0.1 | Specified; pending Gate 0 validation |
| Implementation | Not started |

## MIRAGE-level documents (framing; they create no development tasks)

| Document | Authoritative for |
|---|---|
| [MIRAGE.md](MIRAGE.md) | What MIRAGE is and is not; the scientific loop; evaluation philosophy; evidence maturity (philosophy only) |
| [BENCHMARK_METHODOLOGY.md](BENCHMARK_METHODOLOGY.md) | How MIRAGE constructs ambiguity (paired worlds, controlled non-identifiability) and evaluates experiments (diagnosticity, counterfactual scoring) |
| [DIFFERENTIATION.md](DIFFERENTIATION.md) | The technical and creative contribution, and what we do **not** claim |

## MIRAGE-Bio implementation documents (`mirage-bio/`)

| Document | Authoritative for |
|---|---|
| [ANALYSIS.md](mirage-bio/ANALYSIS.md) | What and why: requirements (FR, NFR, SVR), assumptions, metrics M1–M5, success criteria |
| [DESIGN.md](mirage-bio/DESIGN.md) | How MIRAGE-Bio is implemented: model, tools, schemas, evaluator, baselines |
| [GATE0_SPEC.md](mirage-bio/GATE0_SPEC.md) | What must be scientifically demonstrated before agent integration; the single authority for Gate 0 criteria and outputs |
| [DEVELOPMENT_PLAN.md](mirage-bio/DEVELOPMENT_PLAN.md) | Build order: milestones MS0–MS6, tasks DEV-001 to DEV-019, timeline, stop rules |
| [TEAM_HANDOFF.md](mirage-bio/TEAM_HANDOFF.md) | Immediate team execution: roles, priorities, do-not-do list |
| [TEST_PLAN.md](mirage-bio/TEST_PLAN.md) | Verification: tests T-001 to T-031 |
| [EXPERIMENT_PLAN.md](mirage-bio/EXPERIMENT_PLAN.md) | Agent measurement: matrices, reporting, interpretation, allowed claims |
| [RISKS.md](mirage-bio/RISKS.md) | Risk register |
| [ADR/](mirage-bio/ADR/) | Decision records ADR-001 to ADR-007. **All apply specifically to MIRAGE-Bio.** |

Design-time numerical reference (not the production Gate 0, and not evidence it has
passed): [`experiments/reference/design_validation.py`](../experiments/reference/design_validation.py)
and its [output](../experiments/reference/design_validation_output.txt).

## Precedence when documents overlap

| Question | Document that wins |
|---|---|
| What and why | ANALYSIS |
| How | DESIGN |
| Gate 0 criteria and outputs | GATE0_SPEC (ANALYSIS states the SVRs; GATE0_SPEC states how they pass) |
| When and in what order | DEVELOPMENT_PLAN |
| Who, and what now | TEAM_HANDOFF |
| How we verify | TEST_PLAN |
| How we measure the agent | EXPERIMENT_PLAN |
| How it can fail | RISKS |
| Why a decision was made | ADRs |
| Project identity and methodology | MIRAGE, BENCHMARK_METHODOLOGY, DIFFERENTIATION. These never override MIRAGE-Bio implementation scope. |
