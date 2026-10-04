# Scenario generation

Procedural worlds are generated from an explicit seed and a world mode (`sample_world`). The same seed and the same
public action sequence reproduce the public observations and transitions; different seeds give variation. Policies are
compared on identical seed lists.

| Mode | Samples |
|---|---|
| `SINGLE_FAILURE` | one molecular defect (low stability) |
| `COMPOUND_FAILURE` | aggregation plus a fast-dissociation kinetic defect |
| `ASSAY_FAILURE` | a good molecule with an invalid downstream assay |
| `MODEL_FAILURE` | a good molecule and valid assay with an invalid biological model |
| `MIXED` | a molecule that looks fine on cheap proxies but has an epitope and developability problem (the misleading-proxy trap) |

Two generators exist, selected by `BinderScenarioVersion`:

- **`BASELINE_V1`** (default, frozen). The generator behind Baseline V1. Its worlds carry failures beyond the named
  mechanism (for example `aggregation_kinetic_defect` also fails affinity and developability under `campaign-eval/1`
  labels).
- **`SEMANTICS_V2`**. Draws are constrained so that threshold memberships equal the named primary mechanisms; good
  factors are clipped well inside their healthy range. See [BINDER_ENVIRONMENT](BINDER_ENVIRONMENT.md#scenario-semantics-versions).

Scenario labels are generation controls and reporting archetypes. They are never policy-visible and never force a
mutually exclusive causal model. The benchmark crosses 5 archetypes with disjoint seed sets: Baseline V1 used
development seeds 1000-1049 and held-out 50000-50099 (50 per archetype used); V2 reserves development 1100-1149 and
held-out 60000-60049; PPO training uses its own disjoint ranges (`mirage.rl.randomization`).
