import { ACTION_TYPES, BELIEF_KEYS } from './wire'
import type { BeliefSummary, EpisodeRecord, PolicyComparisonRecord, ResourceState } from './wire'
import { TransportError } from './transport'

/**
 * Guards for payloads crossing the trust boundary into the frontend. They
 * enforce the replay checks in PROVENANCE_AND_REPLAY.md that a client can
 * verify (contiguous steps, schema validity, resource accounting, absence of
 * privileged fields) and fail loudly instead of rendering something unsafe.
 */

const PRIVATE_KEY = /^_|truth|privileged|particle|latent|simulator|hidden|^true_|evaluator_annotation|world_class/i

function fail(where: string, what: string): never {
  throw new TransportError(`Contract violation at ${where}: ${what}`)
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

/** Throws if any object key looks like a privileged / hidden-truth field. */
export function assertPublic(v: unknown, where = '$'): void {
  if (Array.isArray(v)) v.forEach((x, i) => assertPublic(x, `${where}[${i}]`))
  else if (isObj(v)) {
    for (const [k, x] of Object.entries(v)) {
      if (PRIVATE_KEY.test(k)) fail(`${where}.${k}`, 'privileged field in a public payload')
      assertPublic(x, `${where}.${k}`)
    }
  }
}

const num = (v: unknown, where: string) => {
  if (typeof v !== 'number' || !Number.isFinite(v)) fail(where, 'expected a finite number')
  return v
}

export function assertBelief(b: unknown, where: string): asserts b is BeliefSummary {
  if (!isObj(b)) fail(where, 'not an object')
  for (const key of Object.values(BELIEF_KEYS)) {
    const p = num(b[key], `${where}.${key}`)
    if (p < 0 || p > 1) fail(`${where}.${key}`, 'probability outside [0,1]')
  }
  num(b.posterior_entropy, `${where}.posterior_entropy`)
  num(b.effective_sample_size, `${where}.effective_sample_size`)
  if (!isObj(b.continuous_means) || !isObj(b.continuous_variances)) fail(where, 'continuous_means / continuous_variances must be objects')
}

function assertResources(r: unknown, where: string): asserts r is ResourceState {
  if (!isObj(r)) fail(where, 'not an object')
  for (const k of ['budget_remaining', 'sample_remaining', 'simulated_time', 'spr_instrument_health']) num(r[k], `${where}.${k}`)
  if ((r.spr_instrument_health as number) < 0 || (r.spr_instrument_health as number) > 1) fail(`${where}.spr_instrument_health`, 'outside [0,1]')
  if ((r.budget_remaining as number) < 0 || (r.sample_remaining as number) < 0) fail(where, 'negative resource')
}

const sameResources = (a: ResourceState, b: ResourceState) =>
  a.budget_remaining === b.budget_remaining && a.sample_remaining === b.sample_remaining && a.simulated_time === b.simulated_time && a.spr_instrument_health === b.spr_instrument_health

export function assertRecord(raw: unknown, where = 'record'): EpisodeRecord {
  assertPublic(raw, where)
  if (!isObj(raw)) fail(where, 'not an object')
  for (const k of ['contract_version', 'episode_id', 'seed', 'scenario', 'policy', 'initial_state', 'events', 'provenance']) {
    if (!(k in raw)) fail(where, `missing "${k}"`)
  }
  const r = raw as unknown as EpisodeRecord
  if (typeof r.contract_version !== 'string') fail(where, 'contract_version must be a string')
  num(r.seed, `${where}.seed`)
  assertBelief(r.initial_state.belief, `${where}.initial_state.belief`)
  assertResources(r.initial_state.resources, `${where}.initial_state.resources`)
  if (!Array.isArray(r.initial_state.notes)) r.initial_state.notes = []
  if (!Array.isArray(r.events)) fail(where, 'events must be an array')
  if (r.terminal_decision === undefined) r.terminal_decision = null
  if (r.complete === undefined) r.complete = r.terminal_decision !== null

  let prevBelief: BeliefSummary = r.initial_state.belief
  let prevRes: ResourceState = r.initial_state.resources
  r.events.forEach((e, i) => {
    const w = `${where}.events[${i}]`
    if (e.step !== i + 1) fail(w, `non-contiguous step ${e.step}, expected ${i + 1}`)
    if (!ACTION_TYPES.includes(e.action?.action_type)) fail(w, `unknown action_type "${e.action?.action_type}"`)
    assertBelief(e.belief_before, `${w}.belief_before`)
    assertBelief(e.belief_after, `${w}.belief_after`)
    assertResources(e.resources_before, `${w}.resources_before`)
    assertResources(e.resources_after, `${w}.resources_after`)
    if (!sameResources(e.resources_before, prevRes)) fail(w, 'resources_before does not match the previous resources_after (accounting gap)')
    if (e.belief_before.posterior_entropy !== prevBelief.posterior_entropy) fail(w, 'belief_before does not match the previous belief_after')
    if (e.resources_after.budget_remaining > e.resources_before.budget_remaining || e.resources_after.sample_remaining > e.resources_before.sample_remaining)
      fail(w, 'resources increased during an action')
    const kind = e.action.action_type
    if (/^REDESIGN_/.test(kind)) {
      if (e.observation !== null) fail(w, 'redesign actions produce no observation')
      if (!e.active_candidate_after) fail(w, 'redesign events must carry active_candidate_after (the new candidate)')
    }
    if (e.observation) {
      if (!isObj(e.observation.measurements) || Object.keys(e.observation.measurements).length === 0) fail(w, 'observation.measurements must be a non-empty object')
      if ('value' in e.observation || 'metadata' in e.observation) fail(w, 'observations have no scalar value / generic metadata field')
      for (const [k, v] of Object.entries(e.observation.measurements)) num(v, `${w}.observation.measurements.${k}`)
      if (typeof e.observation.quality !== 'string' || e.observation.quality === '') fail(w, 'observation.quality is required')
      if (!Array.isArray(e.observation.notes)) e.observation.notes = []
    }
    prevBelief = e.belief_after
    prevRes = e.resources_after
  })
  return r
}

export function assertComparison(raw: unknown): PolicyComparisonRecord {
  assertPublic(raw, 'comparison')
  if (!isObj(raw) || !Array.isArray(raw.records) || raw.records.length < 2) fail('comparison', 'needs at least two records')
  const c = raw as unknown as PolicyComparisonRecord
  c.records.forEach((r, i) => assertRecord(r, `comparison.records[${i}]`))
  const seeds = new Set(c.records.map((r) => r.seed))
  if (seeds.size !== 1 || !seeds.has(c.seed)) fail('comparison', 'policies must share one seed (identical worlds)')
  const starts = new Set(c.records.map((r) => r.initial_state.candidate.candidate_id))
  if (starts.size !== 1) fail('comparison', 'policies must start from the same candidate')
  return c
}
