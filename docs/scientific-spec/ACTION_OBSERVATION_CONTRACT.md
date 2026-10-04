# Action and observation contract

Canonical names are frozen. Public observations use action_type, candidate_id, measurements: dict[str, float], quality, and optional public notes. Arbitrary generic metadata is forbidden because it becomes a truth-leak channel.

| Action | Public measurements and purpose | Cost, artifact, and transition |
| --- | --- | --- |
| MEASURE_STABILITY | stability_proxy | budget, sample, time; noisy folding evidence |
| MEASURE_SEC | monomer_fraction | budget, sample, time; aggregation evidence before SPR |
| MEASURE_SPR | log_kd and log_koff estimates | budget, sample, time; aggregated input can degrade quality and SPR health |
| MEASURE_EPITOPE | epitope_signal | resources/time; functional epitope evidence |
| MEASURE_DEVELOPABILITY | liability_proxy | resources/time; developability evidence |
| VALIDATE_ASSAY | control_signal | budget/time; assay-integrity evidence |
| ORTHOGONAL_FUNCTION | orthogonal_function_signal | resources/time; separates assay from model explanations |
| REDESIGN_STABILITY | no assay result; new candidate ID | expected stability benefit with weak trade-offs |
| REDESIGN_SOLUBILITY | no assay result; new candidate ID | expected aggregation/developability benefit |
| REDESIGN_INTERFACE | no assay result; new candidate ID | expected affinity/kinetic benefit with small stability/aggregation downside |
| SELECT | terminal decision | ends episode |
| REJECT | terminal decision | ends episode |
| MODEL_INVALID | terminal decision | ends episode |
| ABSTAIN | terminal decision | ends episode |

Observation distributions overlap across mechanisms. A public measurement name describes an assay readout, not a direct truth field; no action returns a perfect latent factor or trivial healthy/failure code. Preconditions include sufficient budget/sample, nonterminal state, and candidate existence. Exact costs, durations, noise scales, quality thresholds, and transition distributions are configurable simulator parameters.
