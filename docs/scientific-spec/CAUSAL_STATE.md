# Factorised causal state

Private hidden state per candidate is **factorised**, not a one-of-N class. It is a `BinderHypothesis`
(`src/mirage/environments/binder/predictive.py`), the same type the belief engine uses for hypothetical particles:

| Factor | Interpretation | Type / range |
|---|---|---|
| `stability` | folding / structural robustness | float in [0, 1] |
| `monomer_fraction` | aggregation tendency (1 = fully monomeric) | float in [0, 1] |
| `log_kd` | equilibrium affinity (log10 M; more negative = tighter) | float |
| `log_koff` | dissociation kinetics (log10 s⁻¹; larger = faster off-rate) | float |
| `functional_epitope` | target engagement relevant to function | bool |
| `developability_liability` | off-target / developability risk | float in [0, 1] |
| `assay_valid` | downstream assay integrity | bool |
| `model_valid` | biological-model (pathway/translation) assumption integrity | bool |

A scenario template sets one or more factors into a failure regime; it does not replace the factorised
representation, and compound failures are valid by construction. Failure *labels* are thresholds on these factors
(see [BINDER_ENVIRONMENT](BINDER_ENVIRONMENT.md#label-rule-inconsistency)), not extra state.

Resource state is separate and public: budget, sample, simulated time, SPR instrument health, plus candidate
generation and lineage. Truth belongs solely to the environment and the privileged evaluator.

All values are synthetic modelling assumptions. `log_kd` and `log_koff` carry units only by convention; no real
molecule is represented.
