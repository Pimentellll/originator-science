import { ACTION_TYPES } from './wire'
import { actionInforms, actionKind, actionLabel, formatMeasurement, isPoorQuality, measurementLabel } from './actions'
import { fmtBudget, fmtP, fmtSample, MECH_LABEL } from './format'
import { MECHANISMS } from './types'
import type { ActionType, CockpitState, EventView, Mechanism } from './types'
import { verdictOf } from './verdict'

export type Focus = 'candidate' | 'evidence' | 'belief' | 'action' | 'resources' | 'timeline' | 'justification'

export interface Beat {
  id: string
  kind: 'failure' | 'evidence' | 'update' | 'redesign' | 'decision' | 'justification'
  heading: string
  body: string[]
  /** Frame to show while this beat is on screen. */
  cursor: number
  /** Cockpit panel the coach points at. */
  focus: Focus
}

const VERB: Partial<Record<ActionType, string>> = {
  SELECT: 'selects',
  REJECT: 'rejects',
  MODEL_INVALID: 'declares the biological model invalid for',
  ABSTAIN: 'abstains on',
}

const mech = (m: Mechanism) => MECH_LABEL[m]

function deltas(e: EventView) {
  return MECHANISMS.map((m) => ({ m, before: e.belief_before?.p[m] ?? e.belief_after.p[m], after: e.belief_after.p[m] }))
    .map((d) => ({ ...d, d: d.after - d.before }))
    .sort((a, b) => Math.abs(b.d) - Math.abs(a.d))
}

function costLine(e: EventView) {
  return `Cost: budget ${fmtBudget(e.cost.budget)}, sample ${fmtSample(e.cost.sample)}.`
}

function evidenceBeat(frames: CockpitState[], i: number): Beat {
  const e = frames[i].events[i]
  const prev = frames[i].events[i - 1]
  const act = e.action_type!
  const lines = [`${actionLabel(act)} on ${e.candidate_id}.`]
  const sprBefore = frames[i].events.slice(0, i).some((x) => x.action_type === 'MEASURE_SPR')
  if (act === 'MEASURE_SEC' && !sprBefore) lines.push('Cheap, low-risk evidence first: SEC reads the monomer fraction before the expensive SPR instrument is used.')
  else if (act === 'MEASURE_SPR' && prev?.kind === 'redesign') lines.push(`After the redesign, MIRAGE measures binding kinetics on the repaired candidate ${e.candidate_id}.`)
  else lines.push(`This assay informs: ${actionInforms(act).map(mech).join(', ') || 'no mechanism directly'}.`)
  const obs = e.observation
  if (obs) {
    const reading = obs.measurements.map((m) => `${measurementLabel(m.name)} ${formatMeasurement(m.name, m.value)}`).join(' · ')
    lines.push(`Reading: ${reading}${isPoorQuality(obs.quality) ? ` (${obs.quality})` : ''}.`)
  }
  if (act === 'MEASURE_SPR') {
    const h = frames[i].resources.spr_health
    lines.push(e.spr_delta < -1e-9 ? `SPR instrument health fell by ${Math.abs(e.spr_delta).toFixed(2)} (now ${h.toFixed(2)}): measuring a badly behaved sample costs the instrument.` : `SPR instrument health is unchanged (${h.toFixed(2)}).`)
  }
  lines.push(costLine(e))
  return { id: `s${e.step}:evidence`, kind: 'evidence', heading: actionLabel(act).toUpperCase(), body: lines, cursor: i, focus: 'evidence' }
}

function updateBeat(frames: CockpitState[], i: number): Beat {
  const e = frames[i].events[i]
  const [top, second] = deltas(e)
  const label = actionLabel(e.action_type!)
  const lines: string[] = []
  if (Math.abs(top.d) >= 0.02) {
    lines.push(`${label} evidence moved the posterior for ${mech(top.m)}: ${fmtP(top.before)} → ${fmtP(top.after)}.`)
    if (second && Math.abs(second.d) >= 0.02) lines.push(`${mech(second.m)} moved ${fmtP(second.before)} → ${fmtP(second.after)}.`)
  } else lines.push(`${label} barely moved the posterior: no mechanism changed by 0.02 or more.`)
  lines.push(`Posterior entropy ${(e.belief_before?.entropy ?? 0).toFixed(2)} → ${e.belief_after.entropy.toFixed(2)}.`)
  lines.push('This is the model posterior, not an empirical biological probability.')
  return { id: `s${e.step}:update`, kind: 'update', heading: 'CAUSAL UPDATE', body: lines, cursor: i, focus: 'belief' }
}

function redesignBeat(frames: CockpitState[], i: number): Beat {
  const e = frames[i].events[i]
  const lines = [`${actionLabel(e.action_type!)}: ${e.candidate_id} is repaired rather than discarded. ${e.result_candidate_id ?? 'A child'} joins the same lineage.`]
  if (e.targets.length) lines.push(`Aimed at: ${e.targets.map(mech).join(', ')}.`)
  if (e.rationale) lines.push(`Policy rationale: ${e.rationale}`)
  lines.push(costLine(e))
  return { id: `s${e.step}:redesign`, kind: 'redesign', heading: actionLabel(e.action_type!).toUpperCase(), body: lines, cursor: i, focus: 'candidate' }
}

function decisionBeat(frames: CockpitState[], i: number): Beat {
  const f = frames[i]
  const e = f.events[i]
  const act = e.action_type!
  const lead = MECHANISMS.map((m) => ({ m, p: e.belief_after.p[m] })).sort((a, b) => b.p - a.p)[0]
  const lines = [`MIRAGE ${VERB[act] ?? 'decides on'} ${e.candidate_id}.`]
  lines.push(lead.p >= 0.5 ? `Basis: the leading explanation is ${mech(lead.m)} at ${fmtP(lead.p)} (model posterior).` : 'Basis: no explanation reaches 0.50 in the posterior.')
  lines.push(`Posterior entropy at the decision: ${e.belief_after.entropy.toFixed(2)}.`)
  return { id: `s${e.step}:decision`, kind: 'decision', heading: 'DECISION', body: lines, cursor: i, focus: 'action' }
}

function justificationBeat(frames: CockpitState[], i: number): Beat {
  const f = frames[i]
  const t = f.terminal!
  const ev = t.evaluation
  const v = verdictOf(ev, t.decision)
  const r = f.resources
  const measured = new Set(f.events.filter((e) => e.observation).map((e) => e.action_type))
  const unrun = ACTION_TYPES.filter((a) => actionKind(a) === 'measurement' && !measured.has(a))
  const redesigns = f.events.filter((e) => e.kind === 'redesign').length
  const experiments = f.events.filter((e) => e.kind === 'measurement').length
  const unresolved = MECHANISMS.map((m) => ({ m, p: f.belief.p[m] })).filter((x) => x.p > 0.1 && x.p < 0.9)
  const lines = [`${v.label}. ${v.explain}`]
  if (ev?.checks?.length) {
    const ok = ev.checks.filter((c) => c.passed).map((c) => c.name.replace(/_/g, ' '))
    const bad = ev.checks.filter((c) => !c.passed).map((c) => c.name.replace(/_/g, ' '))
    lines.push(`Evidence supporting the decision: ${ok.length ? ok.join('; ') : 'none of the evaluator checks passed'}.`)
    if (bad.length) lines.push(`Missing evidence: ${bad.join('; ')}.`)
  }
  lines.push(`Resources consumed: budget ${fmtBudget(r.budget.total - r.budget.remaining)} of ${fmtBudget(r.budget.total)}, sample ${fmtSample(r.sample.total - r.sample.remaining)} of ${fmtSample(r.sample.total)} · ${experiments} experiment${experiments === 1 ? '' : 's'}, ${redesigns} redesign${redesigns === 1 ? '' : 's'}.`)
  lines.push(`Assays not run: ${unrun.length ? unrun.map(actionLabel).join(', ') : 'none'}.`)
  lines.push(unresolved.length ? `Remaining uncertainty: ${unresolved.map((x) => `${mech(x.m)} ${fmtP(x.p)}`).join(', ')} (entropy ${f.belief.entropy.toFixed(2)}).` : `Remaining uncertainty: every mechanism is settled below 0.10 or above 0.90 (entropy ${f.belief.entropy.toFixed(2)}).`)
  return { id: 'justification', kind: 'justification', heading: 'JUSTIFICATION', body: lines, cursor: i, focus: 'justification' }
}

/**
 * The narrated walk through a real campaign, built from the frames revealed so far. Every number
 * comes from the public record or from the token-gated evaluator verdict; no outcome is scripted.
 */
export function buildBeats(frames: CockpitState[]): Beat[] {
  if (frames.length === 0) return []
  const beats: Beat[] = [
    {
      id: 'failure',
      kind: 'failure',
      heading: 'FAILURE',
      body: [
        'The binder failed downstream.',
        'We do not yet know whether the cause is molecular, experimental or biological.',
        `Starting posterior entropy ${frames[0].belief.entropy.toFixed(2)}: every explanation is still open.`,
      ],
      cursor: 0,
      focus: 'candidate',
    },
  ]
  for (let i = 1; i < frames.length; i++) {
    const e = frames[i].events[i]
    if (!e?.action_type) continue
    if (e.kind === 'measurement') beats.push(evidenceBeat(frames, i), updateBeat(frames, i))
    else if (e.kind === 'redesign') beats.push(redesignBeat(frames, i))
    else if (e.kind === 'decision') {
      beats.push(decisionBeat(frames, i))
      if (frames[i].terminal) beats.push(justificationBeat(frames, i))
    }
  }
  return beats
}
