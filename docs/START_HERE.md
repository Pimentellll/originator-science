# MIRAGE implementation start

MIRAGE evaluates autonomous scientific decision-making under causal uncertainty. Its central question is **active identifiability**: can an agent identify which experiment would make a conclusion justified, rather than merely guess a correct label?

## Status

| Area | Status |
| --- | --- |
| Growth regression benchmark | IMPLEMENTED and retained |
| Binder BioPOMDP | IN DEVELOPMENT |
| Particle belief and policy suite | IN DEVELOPMENT |
| PPO / Modal training | PLANNED |
| Scientific Cockpit | PLANNED |

Start with [Architecture](architecture/MIRAGE_ARCHITECTURE.md), then the [Binder environment](scientific-spec/BINDER_ENVIRONMENT.md), [trust boundary](architecture/TRUST_BOUNDARY.md), [work packages](implementation/WORK_PACKAGES.md), and [acceptance gates](implementation/ACCEPTANCE_GATES.md).

The growth/OD benchmark is the original MIRAGE regression benchmark. It remains working code and a regression target; it is not replaced or rewritten by the Binder BioPOMDP.

## Contract precedence

These D0 documents freeze cross-team interfaces and terminology. Existing docs/mirage-bio records the original benchmark and remains historically authoritative for that environment unless a document here explicitly says otherwise. Synthetic parameters and assay behavior are MIRAGE design choices, not biological claims.
