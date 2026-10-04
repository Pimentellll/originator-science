import { BELIEF_KEYS } from './wire'
import type { BenchmarkReportDto, BeliefSummary, DecisionTrace, EpisodeRecord, EpisodeSummaryDto, PolicyComparisonRecord, ResourceState } from './wire'
import { MECHANISMS } from './types'
import type {
  AlternativeView,
  BenchmarkReport,
  Belief,
  CandidateStatus,
  CockpitState,
  DecisionView,
  EpisodeSummary,
  EventView,
  EvidenceLink,
  LineageNode,
  Mechanism,
  PolicyComparison,
  Recommendation,
  Resources,
} from './types'
import { actionInforms, actionKind, actionLabel, canonicalPolicyKey, CANONICAL_POLICIES, isPoorQuality, isTerminalAction, policyInfo } from './actions'

/**
 * Projection: public EpisodeRecord -> frontend frames. Pure and total; the
 * same function serves replay files and live records, so scrubbing, graphing
 * and comparison never depend on how the record arrived.
 */

export function toBelief(b: BeliefSummary): Belief {
  const p = {} as Record<Mechanism, number>
  for (const m of MECHANISMS) p[m] = b[BELIEF_KEYS[m]]
  return { p, localisation: b.failure_localisation ?? null, entropy: b.posterior_entropy, ess: b.effective_sample_size, means: b.continuous_means, variances: b.continuous_variances }
}

function toResources(r: ResourceState, totals: ResourceState): Resources {
  return {
    budget: { remaining: r.budget_remaining, total: totals.budget_remaining },
    sample: { remaining: r.sample_remaining, total: totals.sample_remaining },
    time: { elapsed: r.simulated_time },
    spr_health: r.spr_instrument_health,
  }
}

/** Informed mechanisms register small shifts; spill-over onto others must be material. */
const SHIFT_INFORMED = 0.03
const SHIFT_OTHER = 0.1

/**
 * Support / contradiction is DERIVED from the public belief change, never
 * supplied: a mechanism whose probability rose supports it, one that fell
 * contradicts it. Mechanisms the assay informs but that did not move, or whose
 * reading was poor quality, are unresolved.
 */
export function deriveLinks(before: Belief, after: Belief, informs: Mechanism[], quality: string): EvidenceLink[] {
  const poor = isPoorQuality(quality)
  const links: EvidenceLink[] = []
  for (const m of MECHANISMS) {
    const d = after.p[m] - before.p[m]
    const informed = informs.includes(m)
    const min = informed ? SHIFT_INFORMED : SHIFT_OTHER
    if (poor && informed) links.push({ mechanism: m, relation: 'unresolved', weight: 0.5 })
    else if (d >= min) links.push({ mechanism: m, relation: 'supports', weight: Math.min(1, Math.max(0.25, d / 0.35)) })
    else if (d <= -min) links.push({ mechanism: m, relation: 'contradicts', weight: Math.min(1, Math.max(0.25, -d / 0.35)) })
    else if (informed) links.push({ mechanism: m, relation: 'unresolved', weight: 0.4 })
  }
  return links
}

const costOfEvent = (a: ResourceState, b: ResourceState) => ({
  budget: a.budget_remaining - b.budget_remaining,
  sample: a.sample_remaining - b.sample_remaining,
  time: b.simulated_time - a.simulated_time,
})

function toDecision(d: DecisionTrace | undefined): DecisionView | undefined {
  if (!d) return undefined
  return {
    score: d.score,
    confidence: d.confidence,
    eig: d.expected_information_gain,
    cost: d.estimated_cost,
    risk: d.risk,
    alternatives: (d.alternatives ?? []).map(
      (a): AlternativeView => ({
        action_type: a.action.action_type,
        candidate_id: a.action.candidate_id ?? '',
        score: a.score,
        eig: a.expected_information_gain,
        cost: a.estimated_cost,
        why_not: a.why_not,
      }),
    ),
  }
}

function toRecommendation(
  action: EpisodeRecord['events'][number]['action'],
  rationale: string | null | undefined,
  decision: DecisionTrace | undefined,
): Recommendation {
  const d = toDecision(decision)
  return {
    action_type: action.action_type,
    candidate_id: action.candidate_id ?? '',
    score: d?.score,
    confidence: d?.confidence,
    eig: d?.eig,
    cost: d?.cost,
    rationale: rationale ?? undefined,
    risk: d?.risk,
    discriminates: actionInforms(action.action_type),
    alternatives: d?.alternatives ?? [],
  }
}

export function projectEpisode(record: EpisodeRecord): CockpitState[] {
  const totals = record.initial_state.resources
  const policy = policyInfo(record.policy.name, record.policy.description)
  const scenario = { id: record.scenario.id, title: record.scenario.title, summary: record.scenario.summary }
  const initialBelief = toBelief(record.initial_state.belief)
  const n = record.events.length

  const root: LineageNode = {
    id: record.initial_state.candidate.candidate_id,
    generation: record.initial_state.candidate.generation,
    parent_id: record.initial_state.candidate.parent_candidate_id,
    created_by: null,
    step: 0,
    status: 'current',
  }

  const failure: EventView = {
    id: 's0',
    step: 0,
    kind: 'failure',
    action_type: null,
    candidate_id: root.id,
    title: 'Observed failure',
    observation: null,
    notes: record.initial_state.notes,
    belief_before: null,
    belief_after: initialBelief,
    resources_before: null,
    resources_after: toResources(record.initial_state.resources, totals),
    cost: { budget: 0, sample: 0, time: 0 },
    spr_delta: 0,
    links: [],
    targets: [],
    t_h: record.initial_state.resources.simulated_time,
  }

  // Events and lineage, accumulated once.
  const events: EventView[] = [failure]
  const lineage: LineageNode[] = [root]
  const lineageAt: LineageNode[][] = [[{ ...root }]]
  for (const e of record.events) {
    const before = toBelief(e.belief_before)
    const after = toBelief(e.belief_after)
    const kind = actionKind(e.action.action_type)
    const inform = actionInforms(e.action.action_type)
    const obs = e.observation
    let result: string | undefined
    if (kind === 'redesign' && e.active_candidate_after) {
      const c = e.active_candidate_after
      result = c.candidate_id
      lineage.push({ id: c.candidate_id, generation: c.generation, parent_id: c.parent_candidate_id, created_by: e.action.action_type, step: e.step, status: 'current' })
    }
    events.push({
      id: `s${e.step}`,
      step: e.step,
      kind,
      action_type: e.action.action_type,
      candidate_id: e.candidate_id ?? root.id,
      result_candidate_id: result,
      title: result ? `${actionLabel(e.action.action_type)} → ${result}` : `${actionLabel(e.action.action_type)} · ${e.candidate_id}`,
      observation:
        obs && kind === 'measurement'
          ? { measurements: Object.entries(obs.measurements).map(([name, value]) => ({ name, value })), quality: obs.quality, notes: obs.notes }
          : null,
      notes: [],
      rationale: e.rationale ?? undefined,
      decision: toDecision(e.decision),
      belief_before: before,
      belief_after: after,
      resources_before: toResources(e.resources_before, totals),
      resources_after: toResources(e.resources_after, totals),
      cost: costOfEvent(e.resources_before, e.resources_after),
      spr_delta: e.resources_after.spr_instrument_health - e.resources_before.spr_instrument_health,
      links: kind === 'measurement' && obs ? deriveLinks(before, after, inform, obs.quality) : [],
      targets: kind === 'redesign' ? inform : [],
      t_h: e.resources_after.simulated_time,
    })
    lineageAt.push(lineage.map((l) => ({ ...l })))
  }

  const frames: CockpitState[] = []
  for (let i = 0; i <= n; i++) {
    const evs = events.slice(0, i + 1)
    const last = evs[evs.length - 1]
    const nodes = lineageAt[i].map((l) => ({ ...l }))
    const terminalAction = i > 0 && isTerminalAction(record.events[i - 1].action.action_type) ? record.events[i - 1].action : i === n ? record.terminal_decision : null
    const terminal = i === n && terminalAction !== null && record.terminal_decision !== null

    let current = nodes[nodes.length - 1]
    for (const node of nodes) node.status = node === current ? 'current' : 'superseded'
    if (terminal && terminalAction) {
      const target = nodes.find((x) => x.id === terminalAction.candidate_id) ?? current
      const st: Record<string, CandidateStatus> = { SELECT: 'selected', REJECT: 'rejected', ABSTAIN: 'abstained' }
      if (st[terminalAction.action_type]) target.status = st[terminalAction.action_type]
      current = target
    }

    let recommendation: Recommendation | null = null
    if (!terminal) {
      if (i < n) recommendation = toRecommendation(record.events[i].action, record.events[i].rationale, record.events[i].decision)
      else if (record.pending?.recommendation) {
        const p = record.pending.recommendation
        recommendation = toRecommendation(p.action, p.rationale, p.decision)
      }
    }

    frames.push({
      episode_id: record.episode_id,
      seed: record.seed,
      campaign: record.campaign ?? null,
      step: i,
      total_steps: record.complete ? n : null,
      policy,
      scenario,
      candidate: current,
      lineage: nodes,
      belief: last.belief_after,
      resources: last.resources_after,
      events: evs,
      recommendation,
      status: terminal ? 'terminal' : 'running',
      terminal:
        terminal && terminalAction
          ? {
              decision: terminalAction.action_type,
              candidate_id: terminalAction.candidate_id ?? current.id,
              evaluation: record.evaluation ?? null,
            }
          : null,
      provenance: record.provenance,
      certificate: i === n && record.certificate ? record.certificate : null,
    })
  }
  return frames
}

export function projectSummary(s: EpisodeSummaryDto): EpisodeSummary {
  return { episode_id: s.episode_id, scenario: s.scenario, policy: policyInfo(s.policy.name, s.policy.description), seed: s.seed, provenance: s.provenance }
}

export function projectComparison(c: PolicyComparisonRecord): PolicyComparison {
  return {
    scenario: c.scenario,
    seed: c.seed,
    tracks: c.records.map((r) => ({ policy: policyInfo(r.policy.name, r.policy.description), frames: projectEpisode(r), provenance: r.provenance })),
    not_run: notRunPolicies(c),
    divergence_note: c.divergence_note,
    provenance: c.provenance,
  }
}

/** Every canonical policy without a track is NOT RUN, whatever the source forgot to mention. */
function notRunPolicies(c: PolicyComparisonRecord) {
  const ran = new Set(c.records.map((r) => canonicalPolicyKey(r.policy.name)))
  const why = new Map((c.not_run ?? []).map((n) => [canonicalPolicyKey(n.policy_name), n.reason]))
  return CANONICAL_POLICIES.filter((p) => !ran.has(p.key)).map((p) => ({
    policy: policyInfo(p.key),
    reason: why.get(p.key) ?? 'No replay artifact or benchmark result exists for this policy.',
  }))
}

export function projectBenchmark(b: BenchmarkReportDto): BenchmarkReport {
  return {
    status: b.status,
    provenance: b.provenance,
    generated_at: b.generated_at,
    seed_set: b.seed_set,
    policies: canonicalBenchmarkPolicies(b),
    families: b.families,
    metrics: b.metrics,
    cells: b.cells,
  }
}

/**
 * Canonical policies first (in fixed order), then any extra the report names.
 * A canonical policy the report does not contain stays in the list with no
 * cells, which the Lab renders as NOT RUN.
 */
function canonicalBenchmarkPolicies(b: BenchmarkReportDto) {
  const given = b.policies.map((p) => ({ ...policyInfo(p.name), label: p.label ?? policyInfo(p.name).label }))
  const have = new Set(given.map((p) => canonicalPolicyKey(p.name)))
  const missing = CANONICAL_POLICIES.filter((p) => !have.has(p.key)).map((p) => policyInfo(p.key))
  const order = (n: string) => {
    const i = CANONICAL_POLICIES.findIndex((p) => p.key === canonicalPolicyKey(n))
    return i < 0 ? 99 : i
  }
  return [...given, ...missing].sort((a, b) => order(a.name) - order(b.name))
}

export function notRunReport(label: string, source: 'mock' | 'recorded' | 'live' = 'recorded'): BenchmarkReport {
  return { status: 'not_run', provenance: { source, label }, policies: [], families: [], metrics: [], cells: {} }
}
