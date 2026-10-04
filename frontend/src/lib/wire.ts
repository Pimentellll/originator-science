/**
 * Public wire contract — mirrors the frozen D0 documents:
 *   docs/architecture/FRONTEND_API_CONTRACT.md
 *   docs/architecture/PROVENANCE_AND_REPLAY.md
 *   docs/architecture/BELIEF_AND_POLICY_CONTRACT.md
 *   docs/scientific-spec/ACTION_OBSERVATION_CONTRACT.md
 * and the frozen Python models in src/mirage/core/contracts.py (commit 9fe2f8e),
 * whose field names are used verbatim where they exist.
 *
 * Only transports, adapters and the mock data know these shapes. Components
 * consume the projected `CockpitState` (lib/types.ts), never these DTOs.
 *
 * Where D0 leaves a shape open, the field is marked PROVISIONAL and optional;
 * the UI degrades gracefully when it is absent. There is deliberately no field
 * for simulator truth, evaluator annotations, particles, assay validity or
 * model validity (ADR 0007).
 */

/** Provisional identifier until the backend publishes its own schema version. */
export const CONTRACT_VERSION = 'mirage-public/d0-provisional'

export const ACTION_TYPES = [
  'MEASURE_STABILITY',
  'MEASURE_SEC',
  'MEASURE_SPR',
  'MEASURE_EPITOPE',
  'MEASURE_DEVELOPABILITY',
  'VALIDATE_ASSAY',
  'ORTHOGONAL_FUNCTION',
  'REDESIGN_STABILITY',
  'REDESIGN_SOLUBILITY',
  'REDESIGN_INTERFACE',
  'SELECT',
  'REJECT',
  'MODEL_INVALID',
  'ABSTAIN',
] as const
export type ActionType = (typeof ACTION_TYPES)[number]

export interface ScientificAction {
  action_type: ActionType
  /** Nullable in core/contracts.py (e.g. ABSTAIN). */
  candidate_id: string | null
}

/**
 * Named finite-float measurements (at least one), a required quality label and
 * public notes. No scalar `value`, no generic metadata. Redesign and terminal
 * actions produce NO observation (it is null on the event).
 */
export interface ScientificObservation {
  action_type: ActionType
  candidate_id: string
  measurements: Record<string, number>
  quality: string
  notes: string[]
}

/** Failure marginals are NOT mutually exclusive and do not sum to one. */
export interface BeliefSummary {
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
  /** Optional FailureLocalisation group probabilities. Not mutually exclusive, not a distribution. */
  failure_localisation?: { molecule: number; experiment: number; biological_model: number }
}

export interface ResourceState {
  budget_remaining: number
  sample_remaining: number
  /** Simulated elapsed time, hours. */
  simulated_time: number
  /** SPR instrument health in [0, 1]. */
  spr_instrument_health: number
}

/** `Candidate` in core/contracts.py: lineage metadata only. */
export interface PublicCandidate {
  candidate_id: string
  generation: number
  parent_candidate_id: string | null
}

export interface ResourceCost {
  budget?: number
  sample?: number
  time?: number
}

/** PROVISIONAL: policy-visible reasoning attached to the decision an event executed. */
export interface DecisionTrace {
  score?: number
  confidence?: number
  expected_information_gain?: number
  estimated_cost?: ResourceCost
  risk?: string
  alternatives?: {
    action: ScientificAction
    score?: number
    expected_information_gain?: number
    estimated_cost?: ResourceCost
    why_not?: string
  }[]
}

export interface ScientificEvent {
  episode_id: string
  step: number
  candidate_id: string | null
  action: ScientificAction
  /** null for REDESIGN_* and terminal actions. */
  observation: ScientificObservation | null
  /**
   * PROVISIONAL: the active candidate after the step (AgentState.active_candidate).
   * Required on REDESIGN_* events, where it carries the new candidate.
   */
  active_candidate_after?: PublicCandidate
  belief_before: BeliefSummary
  belief_after: BeliefSummary
  resources_before: ResourceState
  resources_after: ResourceState
  policy_name: string
  /** Optional public rationale (D0). */
  rationale?: string | null
  /** PROVISIONAL extension. */
  decision?: DecisionTrace
}

/** PROVISIONAL: authorised evaluator output, separate from the public trace. Optional. */
export interface EpisodeEvaluation {
  /** null when the episode abstained: correctness is undefined. */
  terminal_correct: boolean | null
  justified: boolean
  lucky_correct?: boolean
  supported_but_wrong?: boolean
  unnecessary_redesigns?: number
  /** True when the decision was an abstention the evidence supports. */
  justified_abstention?: boolean
  /** Named evidence checks behind `justified`. `detail` is the evaluator's public-data reading. */
  checks?: { name: string; passed: boolean; detail?: string }[]
}

export interface PolicyMeta {
  /** e.g. GreedyEIGPolicy, PPOPolicy. */
  name: string
  description?: string
}

export interface Provenance {
  source: 'mock' | 'recorded' | 'live'
  label: string
  code_version?: string
}

/** PROVISIONAL: what the policy would do next, for an in-progress (live) episode. */
export interface PendingState {
  recommendation?: { action: ScientificAction; rationale?: string | null; decision?: DecisionTrace }
}

/** PROVISIONAL: scientific JustificationCertificate. Consumed when the backend supplies it. */
export interface JustificationCertificate {
  threshold_met: boolean
  threshold?: number
  missing_evidence?: string[]
  rationale?: string
}

export interface EpisodeRecord {
  contract_version: string
  episode_id: string
  seed: number
  /** Public scientific profile, e.g. RECEPTOR_BINDER_RESCUE. Never the world class. */
  campaign?: string
  /** Scenario-semantics version recorded with the episode (SEMANTICS_V2, BASELINE_V1). Never the world class. */
  semantics?: string
  /** Neutral public title. NOT the world class (a generation control, never shown). */
  scenario: { id: string; title: string; summary?: string }
  policy: PolicyMeta
  initial_state: {
    candidate: PublicCandidate
    resources: ResourceState
    belief: BeliefSummary
    /** Public description of the observed failure that starts the episode. */
    notes: string[]
  }
  events: ScientificEvent[]
  terminal_decision: ScientificAction | null
  provenance: Provenance
  /** True once no more events can be appended. */
  complete: boolean
  pending?: PendingState
  evaluation?: EpisodeEvaluation
  /** Certificate for the latest state of the record, if the backend provides one. */
  certificate?: JustificationCertificate
}

/** Identical seeded world under several policies (G13). */
export interface PolicyComparisonRecord {
  scenario: { id: string; title: string; summary?: string }
  seed: number
  records: EpisodeRecord[]
  /** Policies that were asked for but have no real artifact. Rendered as NOT RUN, never as a lane. */
  not_run?: { policy_name: string; reason: string }[]
  /** PROVISIONAL optional narrative for the decision point. */
  divergence_note?: string
  provenance: Provenance
}

export interface EpisodeSummaryDto {
  episode_id: string
  scenario: { id: string; title: string; summary?: string }
  policy: PolicyMeta
  seed: number
  provenance: Provenance
}

// ----------------------------------------------------------------- benchmark

export interface BenchmarkMetricDef {
  id: string
  label: string
  direction: 'higher' | 'lower'
  unit?: string
  /** Bar scale upper bound (lower bound is 0). */
  max: number
}

export type BenchmarkCell = { status: 'ok'; value: number; ci?: [number, number]; n: number } | { status: 'not_run' } | { status: 'na' }

export interface BenchmarkReportDto {
  /** 'not_run' => nothing exists; render NOT RUN. */
  status: 'real' | 'mock' | 'not_run'
  provenance: Provenance
  generated_at?: string
  seed_set?: string
  policies: { name: string; label?: string }[]
  /** Reporting archetypes / slices, data-driven. */
  /** `slice`: an overlapping reporting slice (e.g. myopic worlds) excluded from the all-worlds aggregate. */
  families: { id: string; label: string; slice?: boolean }[]
  metrics: BenchmarkMetricDef[]
  /** cells[family][policy_name][metric_id] */
  cells: Record<string, Record<string, Record<string, BenchmarkCell>>>
}

// ------------------------------------------------------ belief key mapping

/** The one place the BeliefSummary spelling is mapped to frontend mechanism keys. */
export const BELIEF_KEYS = {
  folding: 'p_folding_failure',
  aggregation: 'p_aggregation_failure',
  affinity: 'p_affinity_failure',
  kinetic: 'p_kinetic_failure',
  epitope: 'p_epitope_failure',
  developability: 'p_developability_failure',
  assay_invalid: 'p_assay_invalid',
  model_invalid: 'p_model_invalid',
} as const satisfies Record<string, keyof BeliefSummary>
