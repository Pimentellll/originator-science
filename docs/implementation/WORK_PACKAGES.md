# Work packages

Branches and what was integrated into `feat/mirage-integration` (freeze `d182a2c`).

| Branch | Ownership | Integrated content |
|---|---|---|
| `feat/mirage-core-env` | core contracts and Binder BioPOMDP | yes (public contracts, environment, predictive model; A5 scenario semantics landed on integration) |
| `feat/mirage-belief-eig` | particle belief; Random, Fixed, GreedyEIG; Lookahead; B4A | yes (B0-B3, Lookahead `f7ed63f`, gate declaration `20b13fa`, adaptive tempering `97ac554`, audit output) |
| `feat/mirage-eval-api` | evaluator, provenance, replay, API; Baseline V1; V2 preregistration | yes (C0/C1/C2, D0/D1, Baseline V1 `5c47262`, V2 prereg `51843d5`; the empty commit `bb5ba96` was not applied) |
| `feat/mirage-frontend` | frontend only | yes (E0, E1 `6725d45`) |
| `feat/mirage-rl-modal` | Gym adapter, PPO | yes (`223bb2b`); **no Modal code exists**, training is local |
| `docs/mirage-architecture` | research note | yes (`9ea83c5`) |
| `feat/mirage-integration` | integration owner | H0 controller, H1 validation, A5 |

Shared manifests and root-level files are integration-owned. Because integration already held cherry-picked copies of
the early commits under different SHAs, the remaining branch commits were cherry-picked in dependency order and the
branches were then recorded as ancestors with a `-s ours` merge, so pushed SHAs and tags stay reachable.
