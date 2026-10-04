# Action and observation contract

Canonical names are frozen.

| Action | Purpose and public observation | Cost / transition |
| --- | --- | --- |
| MEASURE_STABILITY | stability proxy with uncertainty | consumes budget, sample, time |
| MEASURE_SEC | monomer/aggregation evidence | consumes budget, sample, time; protects decision before SPR |
| MEASURE_SPR | affinity/kinetic signal and quality | consumes budget, sample, time; aggregated input can reduce quality and SPR health |
| MEASURE_EPITOPE | functional epitope evidence | consumes resources and time |
| MEASURE_DEVELOPABILITY | liability proxy | consumes resources and time |
| VALIDATE_ASSAY | assay/control evidence | consumes budget/time; informs assay validity |
| ORTHOGONAL_FUNCTION | alternate functional evidence | consumes resources/time; helps assay/model separation |
| REDESIGN_STABILITY | new lineage candidate | expected stability benefit with weak trade-offs |
| REDESIGN_SOLUBILITY | new lineage candidate | expected aggregation/developability benefit |
| REDESIGN_INTERFACE | new lineage candidate | expected affinity/kinetic benefit with small stability/aggregation downside |
| SELECT | terminal select claim | ends episode |
| REJECT | terminal reject claim | ends episode |
| MODEL_INVALID | terminal model challenge | ends episode |
| ABSTAIN | terminal bounded uncertainty claim | ends episode |

Observation distributions overlap across mechanisms. No action returns a perfect latent factor or a trivial healthy/failure code. Preconditions include sufficient budget/sample, nonterminal state, and candidate existence. Exact costs, durations, noise scales, and transition distributions are configurable simulator parameters.
