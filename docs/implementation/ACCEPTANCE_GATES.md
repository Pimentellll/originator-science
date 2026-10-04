# Acceptance gates

Status at `d182a2c`. "Evidence" is where the claim can be checked; "met" is only used where a test or artifact exists.

| Gate | Requirement | Status | Evidence / note |
|---|---|---|---|
| G0 | Existing MIRAGE (growth benchmark) tests pass | MET | legacy tests in `tests/test_*.py` pass in the full run |
| G1 | Seeded environment deterministic | MET | `tests/binder/`, `tests/core/` |
| G2 | No hidden-truth leakage | MET (tested) | key scanner, API leak guard and sentinel tests; see [TRUST_BOUNDARY](../architecture/TRUST_BOUNDARY.md). The scanner inspects keys, not free text |
| G3 | All experiment actions work | MET | `tests/binder/test_action_execution.py` |
| G4 | Resource and instrument transitions work | MET | `tests/binder/test_resource_transitions.py` |
| G5 | Particle posterior responds to diagnostic evidence | MET (directional); **convergence NOT MET** | `tests/belief/test_belief_directional.py`; the B4A gate fails ([results](../validation/B4A_CONVERGENCE_RESULTS.md)) |
| G6 | Compound failures work | MET | compound world mode; `SEMANTICS_V2` aggregation + kinetic |
| G7 | Random/Fixed/Greedy share the policy contract | MET | `tests/policies/` |
| G8 | PPO uses the same contract | MET (adapter) | `PPOPolicy`, `tests/rl/test_rl_policy.py`; no valid checkpoint exists |
| G9 | Assay/model invalidity can be detected | MET at the evaluator/belief level | `VALIDATE_ASSAY`, `ORTHOGONAL_FUNCTION`; V1 shows model-invalid detection is posterior-noise sensitive |
| G10 | A correct guess differs from a justified conclusion | MET | evaluator + adversarial suite; Baseline V1 reports 7% correct-but-unjustified for GreedyEIG |
| G11 | Event logs replay without a model call | MET | `mirage.provenance.Replay`, `tests/provenance/` |
| G12 | Frontend renders replay | MET | frontend tests and E1 live cockpit |
| G13 | Policies use identical seeded worlds | MET | harness world digests; Baseline V1 |
| G14 | No fabricated benchmark results | MET | Lookahead, PPO and V2 are reported NOT RUN; no placeholder numbers outside watermarked mock data |

Open items that are **not** gates but must not be forgotten: the B4A convergence gate; V2 lock integrity after A5;
Lookahead and PPO evaluation; exposing FailureLocalisation / JustificationCertificate through the API.
