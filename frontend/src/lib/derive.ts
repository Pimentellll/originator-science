import { MECHANISMS, groupOf } from './types'
import type {
  ActionType,
  BenchmarkReport,
  Belief,
  Certificate,
  CockpitState,
  EventView,
  GroupId,
  MetricCell,
  Mechanism,
  PolicyComparison,
  PolicyTrack,
  Relation,
} from './types'
import { actionInforms, actionKind, actionLabel, isPoorQuality } from './actions'
import { ACTION_TYPES } from './wire'
import { fmtBudget, fmtNum, fmtSample } from './format'

// ----------------------------------------------------------------- belief

/** An SPR health drop larger than this is reported as instrument damage; smaller changes are ordinary wear. */
export const SPR_DAMAGE = 0.05
export const ACTIVE_P = 0.5
export const RULED_OUT_P = 0.1
export type MechanismStatus = 'active' | 'ruled_out' | 'unresolved'

export function mechanismStatus(p: number): MechanismStatus {
  if (p >= ACTIVE_P) return 'active'
  if (p <= RULED_OUT_P) return 'ruled_out'
  return 'unresolved'
}

export const beliefSum = (b: Belief) => MECHANISMS.reduce((a, m) => a + b.p[m], 0)

export interface BeliefRow {
  mechanism: Mechanism
  p: number
  prev: number | null
  delta: number | null
  status: MechanismStatus
}

export function beliefRows(frame: CockpitState, prev: CockpitState | null): BeliefRow[] {
  return MECHANISMS.map((m) => {
    const p = frame.belief.p[m]
    const pp = prev ? prev.belief.p[m] : null
    return { mechanism: m, p, prev: pp, delta: pp === null ? null : p - pp, status: mechanismStatus(p) }
  })
}

export const entropySeries = (frames: CockpitState[], upTo: number) => frames.slice(0, upTo + 1).map((f) => f.belief.entropy)

// ------------------------------------------------------------- evidence graph

export type GraphNodeKind = 'failure' | 'action' | 'observation' | 'redesign' | 'decision' | 'mechanism'
export type EdgeRelation = Relation | 'flow' | 'targets'

export interface GraphNode {
  id: string
  kind: GraphNodeKind
  col: 0 | 1 | 2
  row: number
  step: number
  event?: EventView
  mechanism?: Mechanism
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  relation: EdgeRelation
  weight: number
}

export interface EvidenceGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
  rows: number
}

export const mechNodeId = (m: Mechanism) => `m:${m}`
export const obsNodeId = (e: EventView) => `${e.id}:obs`

/** Pure projection of the frame's event log into a graph. No layout pixels here. */
export function buildGraph(frame: CockpitState): EvidenceGraph {
  const nodes: GraphNode[] = []
  const edges: GraphEdge[] = []
  let prevSpine: string | null = null

  for (const ev of frame.events) {
    const kind: GraphNodeKind = ev.kind === 'measurement' ? 'action' : ev.kind
    nodes.push({ id: ev.id, kind, col: 0, row: ev.step, step: ev.step, event: ev })
    if (prevSpine) edges.push({ id: `${prevSpine}=>${ev.id}`, source: prevSpine, target: ev.id, relation: 'flow', weight: 0.5 })
    prevSpine = ev.id

    if (ev.kind === 'measurement' && ev.observation) {
      const oid = obsNodeId(ev)
      nodes.push({ id: oid, kind: 'observation', col: 1, row: ev.step, step: ev.step, event: ev })
      edges.push({ id: `${ev.id}->${oid}`, source: ev.id, target: oid, relation: 'flow', weight: 1 })
      for (const l of ev.links) edges.push({ id: `${oid}~${l.mechanism}`, source: oid, target: mechNodeId(l.mechanism), relation: l.relation, weight: l.weight })
    }
    if (ev.kind === 'redesign') for (const m of ev.targets) edges.push({ id: `${ev.id}^${m}`, source: ev.id, target: mechNodeId(m), relation: 'targets', weight: 0.6 })
  }

  MECHANISMS.forEach((m, i) => nodes.push({ id: mechNodeId(m), kind: 'mechanism', col: 2, row: i, step: -1, mechanism: m }))
  return { nodes, edges, rows: frame.events.length }
}

export function neighbourhood(graph: EvidenceGraph, id: string | null): Set<string> {
  const s = new Set<string>()
  if (!id) return s
  s.add(id)
  for (const e of graph.edges) {
    if (e.source === id) s.add(e.target)
    if (e.target === id) s.add(e.source)
  }
  return s
}

// ------------------------------------------------------------------- timeline

export interface TimelineItem {
  step: number
  t_h: number
  kind: EventView['kind']
  label: string
  action_type: ActionType | null
  eventId: string
  /** SPR health change caused by this step (negative = damage). */
  spr_delta: number
}

export function timelineItems(frames: CockpitState[]): TimelineItem[] {
  const last = frames[frames.length - 1]
  return last.events.map((e) => ({
    step: e.step,
    t_h: e.t_h,
    kind: e.kind,
    label: e.title,
    action_type: e.action_type,
    eventId: e.id,
    spr_delta: e.spr_delta,
  }))
}

// ------------------------------------------------------- candidate dossier

export interface DossierRow {
  candidate_id: string
  step: number
  action_type: ActionType
  quality: string
  measurements: { name: string; value: number }[]
}

/** Every public measurement taken on a candidate, newest last. */
export function dossier(frame: CockpitState, candidateId: string): DossierRow[] {
  return frame.events
    .filter((e) => e.observation && e.candidate_id === candidateId)
    .map((e) => ({ candidate_id: candidateId, step: e.step, action_type: e.action_type!, quality: e.observation!.quality, measurements: e.observation!.measurements }))
}

// ----------------------------------------------------------------- compare

export function divergenceStep(tracks: PolicyTrack[]): number {
  const n = Math.min(...tracks.map((t) => t.frames.length - 1))
  for (let i = 0; i < n; i++) {
    const first = tracks[0].frames[i].recommendation?.action_type
    if (tracks.some((t) => t.frames[i].recommendation?.action_type !== first)) return i
  }
  return -1
}

export interface Counterfactual {
  /** Step index of the frame at which the policies diverge. */
  at: number
  chosen: { policy: string; action: ActionType }
  alternative: { policy: string; label: string; action: ActionType; track: PolicyTrack }
  /** What actually happened one step after the alternative. */
  firstEffect: EventView
  consequences: { kind: 'resource' | 'instrument' | 'belief' | 'campaign'; text: string; severity: 'info' | 'warn' | 'bad' }[]
  simulated: true
}

/**
 * "What if the other policy's action had been taken here?" — answered from the
 * identical-seed comparison, i.e. from public traces only. Returns null when
 * the current frame is not a decision point shared with another policy.
 */
export function counterfactualFor(cmp: PolicyComparison | null, policyName: string, step: number): Counterfactual | null {
  if (!cmp) return null
  const mine = cmp.tracks.find((t) => t.policy.name === policyName)
  const other = cmp.tracks.find((t) => t.policy.name !== policyName)
  if (!mine || !other) return null
  const a = mine.frames[step]?.recommendation
  const b = other.frames[step]?.recommendation
  if (!a || !b || (a.action_type === b.action_type && a.candidate_id === b.candidate_id)) return null
  // Same history so far?  Branches are only comparable at a shared state.
  const shared = mine.frames[step].events.every((e, i) => other.frames[step].events[i]?.action_type === e.action_type)
  if (!shared) return null
  const ev = other.frames[step + 1]?.events[step + 1]
  if (!ev) return null

  const out: Counterfactual['consequences'] = []
  if (b.eig !== undefined) out.push({ kind: 'campaign', text: `Expected information: ${b.eig.toFixed(2)} bit${a.eig !== undefined ? ` (chosen action: ${a.eig.toFixed(2)})` : ''}.`, severity: 'info' })
  if (ev.observation && isPoorQuality(ev.observation.quality))
    out.push({ kind: 'campaign', text: `The reading is ${ev.observation.quality}: ${ev.observation.notes.join(' ') || 'quality flagged by the instrument.'}`, severity: 'warn' })
  if (ev.spr_delta < -SPR_DAMAGE) {
    out.push({ kind: 'instrument', text: `SPR instrument health ${(ev.resources_before?.spr_health ?? 1).toFixed(2)} → ${ev.resources_after.spr_health.toFixed(2)}. Later SPR runs are less reliable.`, severity: 'bad' })
  }
  const dc = ev.cost
  out.push({ kind: 'resource', text: `Costs ${fmtBudget(dc.budget)} budget, ${fmtSample(dc.sample)} sample and ${fmtNum(dc.time)} time units.`, severity: 'info' })
  if (ev.belief_before) {
    const moved = MECHANISMS.map((m) => ({ m, d: ev.belief_after.p[m] - ev.belief_before!.p[m] }))
      .filter((x) => Math.abs(x.d) >= 0.08)
      .sort((x, y) => Math.abs(y.d) - Math.abs(x.d))
      .slice(0, 3)
    if (moved.length) out.push({ kind: 'belief', text: moved.map((x) => `${x.m.replace('_', ' ')} ${x.d > 0 ? '+' : '−'}${Math.abs(x.d).toFixed(2)}`).join(', ') + ' in that branch.', severity: 'info' })
  }
  const end = other.frames[other.frames.length - 1]
  const mineEnd = mine.frames[mine.frames.length - 1]
  if (end.terminal) {
    const ev2 = end.terminal.evaluation
    out.push({
      kind: 'campaign',
      text: `That branch continued for ${end.events.length - 1 - step} more action${end.events.length - 1 - step === 1 ? '' : 's'} and ended in ${actionLabel(end.terminal.decision).toLowerCase()}${
        ev2 ? (ev2.terminal_correct ? ' (evaluated correct)' : ' (evaluated incorrect)') : ''
      }. Final SPR health ${end.resources.spr_health.toFixed(2)} vs ${mineEnd.resources.spr_health.toFixed(2)} here.`,
      severity: ev2 && !ev2.terminal_correct ? 'bad' : 'info',
    })
  }
  return { at: step, chosen: { policy: mine.policy.label, action: a.action_type }, alternative: { policy: other.policy.label, label: actionLabel(b.action_type), action: b.action_type, track: other }, firstEffect: ev, consequences: out, simulated: true }
}

// ----------------------------------------------------------------- benchmark

export const ALL_FAMILIES = '__all__'

/** Mean over families that were run; reports how many contributed. */
export function aggregateCell(report: BenchmarkReport, familyId: string, policyName: string, metricId: string): { cell: MetricCell; of: number; total: number } {
  const fams = familyId === ALL_FAMILIES ? report.families.filter((f) => !f.slice) : report.families.filter((f) => f.id === familyId)
  const cells = fams.map((f) => report.cells[f.id]?.[policyName]?.[metricId]).filter((c): c is MetricCell => !!c)
  const ok = cells.filter((c): c is Extract<MetricCell, { status: 'ok' }> => c.status === 'ok')
  if (ok.length === 0) return { cell: cells.every((c) => c.status === 'na') && cells.length ? { status: 'na' } : { status: 'not_run' }, of: 0, total: fams.length }
  const n = ok.reduce((a, c) => a + c.n, 0)
  const value = ok.reduce((a, c) => a + c.value * c.n, 0) / n
  const ci = familyId !== ALL_FAMILIES && ok.length === 1 ? ok[0].ci : undefined
  return { cell: { status: 'ok', value, ...(ci ? { ci } : {}), n }, of: ok.length, total: fams.length }
}

// ------------------------------------------------------------ justification

export interface Justification {
  /** Highest-probability mechanism, only if it clears the leading threshold. */
  leading: { mechanism: Mechanism; p: number; group: GroupId } | null
  /** Highest-probability mechanism that is neither leading nor ruled out. */
  alternative: { mechanism: Mechanism; p: number } | null
  entropy: { now: number; start: number }
  /** Assays that could still move an unresolved mechanism on the ACTIVE candidate. */
  required: { action: ActionType; resolves: { mechanism: Mechanism; p: number }[]; reason: string }[]
  /** From the backend's JustificationCertificate. null = not available; never inferred here. */
  certificate: Certificate | null
}

const SETTLED_HIGH = 0.9

/**
 * "Is this conclusion justified?" from public data only. It lists what the belief and the
 * measurement log show; it deliberately does NOT decide whether the evidence threshold is met.
 * That verdict belongs to the scientific JustificationCertificate.
 */
export function justification(frame: CockpitState, start: CockpitState): Justification {
  const rows = MECHANISMS.map((m) => ({ m, p: frame.belief.p[m] })).sort((a, b) => b.p - a.p)
  const top = rows[0]
  const leading = top.p >= ACTIVE_P ? { mechanism: top.m, p: top.p, group: groupOf(top.m) } : null
  const alt = rows.find((r) => r.m !== leading?.mechanism && r.p > RULED_OUT_P && r.p < SETTLED_HIGH)

  const measured = frame.events.filter((e) => e.observation && e.candidate_id === frame.candidate.id)
  const reliable = new Set(measured.filter((e) => !isPoorQuality(e.observation!.quality)).map((e) => e.action_type))
  const poor = new Set(measured.filter((e) => isPoorQuality(e.observation!.quality)).map((e) => e.action_type))
  const unresolved = rows.filter((r) => r.p > RULED_OUT_P && r.p < SETTLED_HIGH)

  const byAction = new Map<ActionType, { mechanism: Mechanism; p: number }[]>()
  for (const r of unresolved)
    for (const a of ALL_MEASUREMENTS) {
      if (reliable.has(a) || !actionInforms(a).includes(r.m)) continue
      byAction.set(a, [...(byAction.get(a) ?? []), { mechanism: r.m, p: r.p }])
    }
  const required = [...byAction]
    .map(([action, resolves]) => ({
      action,
      resolves: resolves.sort((x, y) => y.p - x.p),
      reason: poor.has(action) ? 'Earlier reading was poor quality; repeat on a clean sample' : 'Not yet measured on the active candidate',
    }))
    .sort((a, b) => b.resolves.reduce((s, r) => s + Math.min(r.p, 1 - r.p), 0) - a.resolves.reduce((s, r) => s + Math.min(r.p, 1 - r.p), 0))
    .slice(0, 3)

  return { leading, alternative: alt ? { mechanism: alt.m, p: alt.p } : null, entropy: { now: frame.belief.entropy, start: start.belief.entropy }, required, certificate: frame.certificate }
}

const ALL_MEASUREMENTS: ActionType[] = ACTION_TYPES.filter((a) => actionKind(a) === 'measurement')
