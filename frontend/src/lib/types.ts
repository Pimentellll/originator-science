/**
 * Frontend state: what components consume. Produced by `lib/project.ts` from
 * public EpisodeRecords. Contains no wire spelling and no hidden truth.
 */
import type { ActionType, Provenance } from './wire'

export type { ActionType, Provenance }

export const MECHANISMS = ['folding', 'aggregation', 'affinity', 'kinetic', 'epitope', 'developability', 'assay_invalid', 'model_invalid'] as const
export type Mechanism = (typeof MECHANISMS)[number]

/** Explanations where the molecule is not the thing that is wrong. */
export const NON_MOLECULAR: readonly Mechanism[] = ['assay_invalid', 'model_invalid']

export interface Belief {
  /** Independent marginals. NOT a distribution: they need not sum to 1. */
  p: Record<Mechanism, number>
  entropy: number
  ess: number | null
  means: Record<string, number>
  variances: Record<string, number>
}

export interface Resources {
  budget: { remaining: number; total: number }
  sample: { remaining: number; total: number }
  time: { elapsed: number }
  /** [0, 1] */
  spr_health: number
}

export interface ActionCost {
  budget: number
  sample: number
  time: number
}

export type Relation = 'supports' | 'contradicts' | 'unresolved'

export interface EvidenceLink {
  mechanism: Mechanism
  relation: Relation
  /** 0..1 strength for edge weight. Derived from the public belief change. */
  weight: number
}

export interface Measurement {
  name: string
  value: number
}

export interface ObservationView {
  measurements: Measurement[]
  quality: string
  notes: string[]
}

export interface AlternativeView {
  action_type: ActionType
  candidate_id: string
  score?: number
  eig?: number
  cost?: Partial<ActionCost>
  why_not?: string
}

export interface DecisionView {
  score?: number
  confidence?: number
  eig?: number
  cost?: Partial<ActionCost>
  risk?: string
  alternatives: AlternativeView[]
}

export type EventKind = 'failure' | 'measurement' | 'redesign' | 'decision'

export interface EventView {
  /** `s{step}` */
  id: string
  step: number
  kind: EventKind
  action_type: ActionType | null
  candidate_id: string
  /** Redesign only: the candidate this action created. */
  result_candidate_id?: string
  title: string
  observation: ObservationView | null
  /** Initial failure: public description lines. */
  notes: string[]
  rationale?: string
  decision?: DecisionView
  belief_before: Belief | null
  belief_after: Belief
  resources_before: Resources | null
  resources_after: Resources
  /** Actual resources consumed by this event (before − after). */
  cost: ActionCost
  /** Change in SPR health caused by this event (negative = damage). */
  spr_delta: number
  links: EvidenceLink[]
  /** Mechanisms a redesign is aimed at. */
  targets: Mechanism[]
  t_h: number
}

export type CandidateStatus = 'current' | 'superseded' | 'selected' | 'rejected' | 'abstained'

export interface LineageNode {
  id: string
  generation: number
  parent_id: string | null
  created_by: ActionType | null
  step: number
  status: CandidateStatus
}

export interface Recommendation {
  action_type: ActionType
  candidate_id: string
  score?: number
  confidence?: number
  eig?: number
  cost?: Partial<ActionCost>
  rationale?: string
  risk?: string
  discriminates: Mechanism[]
  alternatives: AlternativeView[]
}

export interface PolicyInfo {
  name: string
  label: string
  description?: string
}

export interface ScenarioInfo {
  id: string
  title: string
  summary?: string
}

export interface TerminalView {
  decision: ActionType
  candidate_id: string
  /** Authorised evaluator output, only when attached. */
  evaluation: {
    terminal_correct: boolean
    justified: boolean
    compound_recognised?: boolean | null
    assay_invalid_detected?: boolean | null
    model_invalid_detected?: boolean | null
    unnecessary_redesigns?: number
    decision_calibration_error?: number
  } | null
}

export interface CockpitState {
  episode_id: string
  seed: number
  step: number
  /** Known episode length; null while a live episode is still open-ended. */
  total_steps: number | null
  policy: PolicyInfo
  scenario: ScenarioInfo
  candidate: LineageNode
  lineage: LineageNode[]
  belief: Belief
  resources: Resources
  events: EventView[]
  /** What the policy would do next. null when terminal or not supplied. */
  recommendation: Recommendation | null
  status: 'running' | 'terminal'
  terminal: TerminalView | null
  provenance: Provenance
}

// ----------------------------------------------------- session / transport

export type SessionMode = 'live' | 'replay'

export interface PolicyTrack {
  policy: PolicyInfo
  frames: CockpitState[]
}

export interface PolicyComparison {
  scenario: ScenarioInfo
  seed: number
  tracks: PolicyTrack[]
  divergence_note?: string
  provenance: Provenance
}

export interface EpisodeSummary {
  episode_id: string
  scenario: ScenarioInfo
  policy: PolicyInfo
  seed: number
  provenance: Provenance
}

export interface MetricInfo {
  id: string
  label: string
  direction: 'higher' | 'lower'
  unit?: string
  max: number
}

export type MetricCell = { status: 'ok'; value: number; ci?: [number, number]; n: number } | { status: 'not_run' } | { status: 'na' }

export interface BenchmarkReport {
  status: 'real' | 'mock' | 'not_run'
  provenance: Provenance
  generated_at?: string
  seed_set?: string
  policies: PolicyInfo[]
  families: { id: string; label: string; slice?: boolean }[]
  metrics: MetricInfo[]
  cells: Record<string, Record<string, Record<string, MetricCell>>>
}
