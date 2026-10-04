/**
 * Real API DTOs — mirrors src/mirage/api/dto.py and
 * src/mirage/evaluation/campaign/aggregate.py (feat/mirage-eval-api, 0c0d05e).
 *
 * Only liveApiTransport.ts and fromApi.ts import this file. Anything the API
 * adds later goes here first, then through fromApi.ts; components never see it.
 */
import type { ActionType } from './wire'

export interface ApiCandidate {
  candidate_id: string
  generation: number
  parent_candidate_id: string | null
}

export interface ApiResources {
  budget_remaining: number
  sample_remaining: number
  simulated_time: number
  spr_instrument_health: number
}

export interface ApiAction {
  action_type: ActionType
  candidate_id: string | null
}

export interface ApiObservation {
  action_type: ActionType
  candidate_id: string
  measurements: Record<string, number>
  quality: string
  notes: string[]
}

export interface ApiBelief {
  p_folding_failure: number
  p_aggregation_failure: number
  p_affinity_failure: number
  p_kinetic_failure: number
  p_epitope_failure: number
  p_developability_failure: number
  p_assay_invalid: number
  p_model_invalid: number
  posterior_entropy: number
  continuous_means: Record<string, number>
  continuous_variances: Record<string, number>
  effective_sample_size: number
  /** NOT in the API yet. FailureLocalisation group probabilities, consumed if/when present. */
  failure_localisation?: { molecule: number; experiment: number; biological_model: number }
}

export interface ApiPublicState {
  episode_id: string
  terminal: boolean
  active_candidate: ApiCandidate
  candidates: ApiCandidate[]
  resources: ApiResources
  observations: ApiObservation[]
  belief: ApiBelief | null
  available_actions: ApiAction[]
  /** NOT in the API yet. Scientific JustificationCertificate, consumed if/when present. */
  justification_certificate?: ApiCertificate
}

export interface ApiEvent {
  episode_id: string
  step: number
  candidate_id: string
  action: ApiAction
  observation: ApiObservation | null
  child_candidate_id: string | null
  belief_before: ApiBelief | null
  belief_after: ApiBelief | null
  resources_before: ApiResources
  resources_after: ApiResources
  policy_name: string
  rationale: string | null
}

export interface ApiStep {
  event: ApiEvent
  state: ApiPublicState
}

export interface ApiRecommendation {
  episode_id: string
  policy_name: string
  action: ApiAction
}

export interface ApiReplay {
  episode_id: string
  complete: boolean
  schema_version: string
  contract_version: string
  environment_id: string
  code_version: string
  seed: number
  policy_name: string
  initial_candidates: ApiCandidate[]
  initial_resources: ApiResources
  events: ApiEvent[]
  terminal_decision: ApiAction | null
  justification_certificate?: ApiCertificate
}

/** PROVISIONAL shape for the scientific JustificationCertificate. */
export interface ApiCertificate {
  threshold_met: boolean
  threshold?: number
  missing_evidence?: string[]
  rationale?: string
}

/**
 * Authorised per-episode verdict. PROVISIONAL: H0 ships no such route. It must live under the
 * token-gated /benchmarks prefix, because the public leak guard forbids the keys `correct` and
 * `justified` on every other route. Truth-derived diagnostics (compound / assay / model
 * detection) are deliberately not read by the frontend.
 */
export interface ApiEpisodeEvaluation {
  episode_id: string
  evaluator_version: string
  decision: string | null
  correct: boolean | null
  justified: boolean
  lucky_correct?: boolean
  supported_but_wrong?: boolean
  unnecessary_redesigns?: number
  justification_checks?: { name: string; passed: boolean }[]
}

// ----------------------------------------------------------------- benchmark

export interface ApiRate {
  k: number
  n: number
  rate: number | null
  lo: number | null
  hi: number | null
}

export interface ApiGroupSummary {
  n_episodes: number
  terminated: ApiRate
  correct: ApiRate
  justified: ApiRate
  lucky_correct: ApiRate
  supported_but_wrong: ApiRate
  abstained: ApiRate
  abstention_appropriate: ApiRate
  compound_recognized: ApiRate
  assay_invalid_detected: ApiRate
  model_invalid_detected: ApiRate
  unnecessary_redesign_episodes: ApiRate
  premature_aggregated_spr_episodes: ApiRate
  mean_budget_spent: number | null
  mean_sample_used: number | null
  mean_time_elapsed: number | null
  mean_action_count: number | null
  mean_spr_health_lost: number | null
  mean_terminal_brier: number | null
  mean_decision_calibration_error: number | null
  exploitation_flag_counts: Record<string, number>
  // Added by the evaluator's C2 work. Optional so older summaries still parse.
  justified_abstention?: ApiRate
  localisation_accuracy?: ApiRate
  mechanism_precision?: number | null
  mechanism_recall?: number | null
  mechanism_f1?: number | null
  compound_mechanism_f1?: number | null
  mean_terminal_posterior_entropy?: number | null
  mean_experiments?: number | null
  correct_redesign_rate?: ApiRate
  rescued?: ApiRate
  proxy_exploitation_episodes?: ApiRate
  reward_hacking_incident_episodes?: ApiRate
}

export interface ApiPolicySummary {
  policy_name: string
  overall: ApiGroupSummary
  by_scenario_class: Record<string, ApiGroupSummary>
  by_regime: Record<string, ApiGroupSummary>
  by_archetype?: Record<string, ApiGroupSummary>
}

export interface ApiBenchmarkSummary {
  benchmark_id: string
  evaluator_version: string
  seeds: number[]
  policies: Record<string, ApiPolicySummary>
}
