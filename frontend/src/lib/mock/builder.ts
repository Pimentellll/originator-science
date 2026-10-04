import { ACTION_TYPES, BELIEF_KEYS, CONTRACT_VERSION } from '../wire'
import type {
  ActionType,
  BeliefSummary,
  DecisionTrace,
  EpisodeEvaluation,
  EpisodeRecord,
  PublicCandidate,
  ResourceCost,
  ResourceState,
  ScientificEvent,
} from '../wire'
import { MECHANISMS } from '../types'

/**
 * Authoring helper for DEV / MOCK episodes. Takes compact step specs and emits
 * canonical public EpisodeRecords (wire shape), so the mocks exercise the same
 * validation + projection path as a real backend record.
 */

export const MOCK_PROVENANCE = { source: 'mock' as const, label: 'DEV / MOCK · authored for frontend development, not a simulator run' }

export const BUDGET_TOTAL = 5500
export const SAMPLE_TOTAL = 520

export const COST: Record<ActionType, Required<ResourceCost>> = {
  MEASURE_STABILITY: { budget: 150, sample: 15, time: 2 },
  MEASURE_SEC: { budget: 210, sample: 30, time: 3 },
  MEASURE_SPR: { budget: 640, sample: 40, time: 6 },
  MEASURE_EPITOPE: { budget: 450, sample: 30, time: 8 },
  MEASURE_DEVELOPABILITY: { budget: 180, sample: 20, time: 4 },
  VALIDATE_ASSAY: { budget: 260, sample: 20, time: 10 },
  ORTHOGONAL_FUNCTION: { budget: 320, sample: 25, time: 12 },
  REDESIGN_STABILITY: { budget: 1400, sample: 150, time: 72 },
  REDESIGN_SOLUBILITY: { budget: 1400, sample: 150, time: 72 },
  REDESIGN_INTERFACE: { budget: 1400, sample: 150, time: 72 },
  SELECT: { budget: 0, sample: 0, time: 0 },
  REJECT: { budget: 0, sample: 0, time: 0 },
  MODEL_INVALID: { budget: 0, sample: 0, time: 0 },
  ABSTAIN: { budget: 0, sample: 0, time: 0 },
}

const h = (p: number) => (p <= 0 || p >= 1 ? 0 : -(p * Math.log2(p) + (1 - p) * Math.log2(1 - p)))
/** Mock-only: a deterministic stand-in for the particle posterior's effective sample size. */
const ESS = [512, 447, 409, 468, 392, 503, 431, 486, 455]

/** Marginals in MECHANISMS order: folding, aggregation, affinity, kinetic, epitope, developability, assay_invalid, model_invalid. */
export type P8 = [number, number, number, number, number, number, number, number]

export interface Continuous {
  means: Record<string, number>
  variances: Record<string, number>
}

export function belief(p: P8, c: Continuous, step: number): BeliefSummary {
  const out = {} as Record<string, number>
  MECHANISMS.forEach((m, i) => (out[BELIEF_KEYS[m]] = p[i]))
  return {
    ...(out as unknown as BeliefSummary),
    posterior_entropy: +p.reduce((a, x) => a + h(x), 0).toFixed(4),
    continuous_means: c.means,
    continuous_variances: c.variances,
    effective_sample_size: ESS[step % ESS.length],
  }
}

type Alt = [action: ActionType, score: number, eig: number | undefined, why: string]

export function decision(o: { score: number; confidence: number; eig?: number; risk: string; alts: Alt[]; candidate: string }): DecisionTrace {
  return {
    score: o.score,
    confidence: o.confidence,
    expected_information_gain: o.eig,
    risk: o.risk,
    alternatives: o.alts.map(([a, score, eig, why]) => ({
      action: { action_type: a, candidate_id: o.candidate },
      score,
      expected_information_gain: eig,
      estimated_cost: COST[a],
      why_not: why,
    })),
  }
}

export interface StepSpec {
  action: ActionType
  /** Candidate acted on; defaults to the active one. */
  candidate?: string
  /** Redesign: id of the new candidate. */
  newCandidate?: string
  measurements?: Record<string, number>
  quality?: string
  notes?: string[]
  /** Absolute SPR health after the step; defaults to unchanged. */
  spr?: number
  /** Per-step cost override. */
  cost?: Partial<ResourceCost>
  p: P8
  continuous: Continuous
  rationale: string
  decision: DecisionTrace
}

export interface RecordSpec {
  id: string
  seed: number
  scenario: EpisodeRecord['scenario']
  policy: EpisodeRecord['policy']
  candidate: string
  notes: string[]
  p0: P8
  continuous0: Continuous
  steps: StepSpec[]
  evaluation?: EpisodeEvaluation
}

export function buildRecord(spec: RecordSpec): EpisodeRecord {
  const root: PublicCandidate = { candidate_id: spec.candidate, generation: 0, parent_candidate_id: null }
  let active = root
  let res: ResourceState = { budget_remaining: BUDGET_TOTAL, sample_remaining: SAMPLE_TOTAL, simulated_time: 0, spr_instrument_health: 1 }
  const initialRes = res
  let bel = belief(spec.p0, spec.continuous0, 0)
  const initialBelief = bel
  const events: ScientificEvent[] = []

  spec.steps.forEach((s, i) => {
    if (!ACTION_TYPES.includes(s.action)) throw new Error(`bad action ${s.action}`)
    const candidate = s.candidate ?? active.candidate_id
    const c = { ...COST[s.action], ...s.cost }
    const after: ResourceState = {
      budget_remaining: res.budget_remaining - c.budget,
      sample_remaining: res.sample_remaining - c.sample,
      simulated_time: res.simulated_time + c.time,
      spr_instrument_health: s.spr ?? res.spr_instrument_health,
    }
    const redesign = s.action.startsWith('REDESIGN_')
    const nextActive: PublicCandidate = redesign
      ? { candidate_id: s.newCandidate!, generation: active.generation + 1, parent_candidate_id: candidate }
      : active
    const belAfter = belief(s.p, s.continuous, i + 1)
    events.push({
      episode_id: spec.id,
      step: i + 1,
      candidate_id: candidate,
      action: { action_type: s.action, candidate_id: candidate },
      observation: s.measurements
        ? { action_type: s.action, candidate_id: candidate, measurements: s.measurements, quality: s.quality ?? 'good', notes: s.notes ?? [] }
        : null,
      ...(redesign ? { active_candidate_after: nextActive } : {}),
      belief_before: bel,
      belief_after: belAfter,
      resources_before: res,
      resources_after: after,
      policy_name: spec.policy.name,
      rationale: s.rationale,
      decision: { estimated_cost: COST[s.action], ...s.decision },
    })
    res = after
    bel = belAfter
    active = nextActive
  })

  const last = events[events.length - 1]
  return {
    contract_version: CONTRACT_VERSION,
    episode_id: spec.id,
    seed: spec.seed,
    scenario: spec.scenario,
    policy: spec.policy,
    initial_state: { candidate: root, resources: initialRes, belief: initialBelief, notes: spec.notes },
    events,
    terminal_decision: last.action,
    provenance: MOCK_PROVENANCE,
    complete: true,
    ...(spec.evaluation ? { evaluation: spec.evaluation } : {}),
  }
}
