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

export type GroupId = 'molecule' | 'experiment' | 'biological_model'

/**
 * Where the failure is localised. Groups are for reading, not for normalising: members stay
 * independent probabilities, and a group's own probability exists only if the backend's
 * FailureLocalisation supplies it.
 */
export const MECHANISM_GROUPS: { id: GroupId; label: string; sub?: string; members: readonly Mechanism[] }[] = [
  { id: 'molecule', label: 'MOLECULE', members: ['folding', 'aggregation', 'affinity', 'kinetic', 'epitope', 'developability'] },
  { id: 'experiment', label: 'EXPERIMENT', sub: 'assay validity', members: ['assay_invalid'] },
  { id: 'biological_model', label: 'BIOLOGICAL MODEL', sub: 'model validity', members: ['model_invalid'] },
]

export const groupOf = (m: Mechanism): GroupId => MECHANISM_GROUPS.find((g) => g.members.includes(m))!.id

export interface Localisation {
  molecule: number
  experiment: number
  biological_model: number
}

export interface Belief {
  /** Independent marginals. NOT a distribution: they need not sum to 1. */
  p: Record<Mechanism, number>
  /** Group-level FailureLocalisation probabilities, only when the backend supplies them. */
  localisation: Localisation | null
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
  /** baseline | myopic | campaign (lookahead / PPO) | mock (authored illustration) | other */
  family: 'baseline' | 'myopic' | 'campaign' | 'mock' | 'other'
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
    terminal_correct: boolean | null
    justified: boolean
    lucky_correct?: boolean
    supported_but_wrong?: boolean
    unnecessary_redesigns?: number
    justified_abstention?: boolean
    checks?: { name: string; passed: boolean; detail?: string }[]
  } | null
}

export interface CockpitState {
  episode_id: string
  seed: number
  /** Public scientific profile, e.g. RECEPTOR_BINDER_RESCUE. */
  campaign: string | null
  /** Scenario-semantics version recorded with the episode, when the backend reports it. */
  semantics: string | null
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
  /** Scientific JustificationCertificate for this frame; null when the backend does not supply one. */
  certificate: Certificate | null
}

export interface Certificate {
  threshold_met: boolean
  threshold?: number
  missing_evidence?: string[]
  rationale?: string
}

// ----------------------------------------------------- session / transport

export type SessionMode = 'live' | 'replay'

export interface PolicyTrack {
  policy: PolicyInfo
  frames: CockpitState[]
  provenance: Provenance
}

export interface NotRunPolicy {
  policy: PolicyInfo
  reason: string
}

export interface PolicyComparison {
  scenario: ScenarioInfo
  seed: number
  tracks: PolicyTrack[]
  /** Canonical policies with no real artifact. Always shown, as NOT RUN. */
  not_run: NotRunPolicy[]
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

// ------------------------------------------------------- launcher / system

/** How a campaign is driven: the policy runs it, or the person picks each action. */
export type Control = 'auto' | 'manual'

/** Orchestration choices made by the human running the demo. None of this is policy input. */
export interface LaunchConfig {
  /** Showcase id or world-mode name; null = the server's default scenario. */
  scenario: string | null
  /** SEMANTICS_V2 | BASELINE_V1; null = the server's default. */
  semantics: string | null
  policy: string | null
  seed: number
  control: Control
  guided: boolean
}

export interface PolicyEntry {
  name: string
  label: string
  kind: string
  available: boolean
  description: string
  reason: string | null
}

export interface ScenarioEntry {
  id: string
  title: string
  summary: string
  /** World-mode spelling used by `./mirage demo --scenario`. */
  cli_name: string
  is_default: boolean
}

export interface SystemVersion {
  mirage_version: string
  git_sha: string
  git_dirty: boolean | null
  commit_date: string | null
  api_version: string
  contract_version: string
  semantics_default: string
  semantics_available: string[]
  python_version: string
}

/** Public/system-safe catalogue served by the backend. Absent fields mean the server predates them. */
export interface Catalogue {
  version: SystemVersion | null
  /** null = the server has no /policies route; the configured list is used instead. */
  policies: PolicyEntry[] | null
  scenarios: ScenarioEntry[] | null
}

export interface SystemCheck {
  name: string
  status: 'pass' | 'fail' | 'skip'
  detail: string
}

export interface SystemReport {
  reachable: boolean
  checks: SystemCheck[]
  catalogue: Catalogue
  note?: string
}
