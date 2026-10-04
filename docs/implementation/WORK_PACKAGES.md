# Work packages

| Branch | Ownership |
| --- | --- |
| feat/mirage-core-env | core contracts and Binder BioPOMDP |
| feat/mirage-belief-eig | particle belief; Random, Fixed, GreedyEIG |
| feat/mirage-rl-modal | Gym adapter, PPO, Modal |
| feat/mirage-eval-api | evaluator, provenance, replay, API |
| feat/mirage-frontend | frontend only |
| feat/mirage-integration | integration owner |

Shared manifests and root-level files are integration-owned. Each work package may depend only on frozen public contracts, not private environment internals.
