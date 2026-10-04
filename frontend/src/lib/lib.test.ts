import { describe, expect, it } from 'vitest'
import { caseAGreedy, caseAMirage, caseB, comparisonCase1, mockBenchmark, mockSource } from './mock'
import { assertComparison, assertPublic, assertRecord } from './validate'
import { beliefRows, buildGraph, counterfactualFor, aggregateCell, ALL_FAMILIES, divergenceStep, mechanismStatus, timelineItems } from './derive'
import { projectComparison, projectEpisode, deriveLinks, toBelief } from './project'
import { ReplayTransport } from './replayTransport'
import { LiveApiTransport } from './liveApiTransport'
import { adaptBenchmark } from './adapters'
import { MECHANISMS } from './types'
import type { EpisodeRecord } from './wire'

const records = [caseAMirage, caseAGreedy, caseB]
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x))
const label = (r: EpisodeRecord) => `${r.episode_id}`

describe('D0 contract conformance of the mock records', () => {
  it.each(records.map((r) => [label(r), r] as const))('%s passes the replay validator', (_n, r) => {
    expect(() => assertRecord(clone(r))).not.toThrow()
  })

  it('SEC observations expose monomer_fraction; SPR exposes log_kd and log_koff (structured, no scalar value)', () => {
    for (const r of records)
      for (const e of r.events) {
        if (e.action.action_type === 'MEASURE_SEC') expect(Object.keys(e.observation!.measurements)).toEqual(['monomer_fraction'])
        if (e.action.action_type === 'MEASURE_SPR') expect(Object.keys(e.observation!.measurements).sort()).toEqual(['log_kd', 'log_koff'])
        if (e.observation) {
          expect(Object.keys(e.observation).sort()).toEqual(['action_type', 'candidate_id', 'measurements', 'notes', 'quality'])
          expect(e.observation.quality.length).toBeGreaterThan(0)
          expect(Object.values(e.observation.measurements).every((v) => Number.isFinite(v))).toBe(true)
        }
      }
  })

  it('redesign and terminal actions carry no observation; redesign carries the new candidate', () => {
    for (const r of records)
      for (const e of r.events) {
        if (e.action.action_type.startsWith('REDESIGN_')) {
          expect(e.observation).toBeNull()
          expect(e.active_candidate_after!.parent_candidate_id).toBe(e.candidate_id)
        }
        if (['SELECT', 'REJECT', 'ABSTAIN', 'MODEL_INVALID'].includes(e.action.action_type)) expect(e.observation).toBeNull()
      }
  })

  it('contains no privileged / hidden-truth keys anywhere', () => {
    for (const r of records) expect(() => assertPublic(r)).not.toThrow()
    expect(() => assertPublic(mockBenchmark)).not.toThrow()
    expect(() => assertPublic(comparisonCase1)).not.toThrow()
  })

  it('does not name the scenario world class in public text', () => {
    const blob = JSON.stringify(records).toUpperCase()
    for (const w of ['COMPOUND_FAILURE', 'ASSAY_FAILURE', 'MODEL_FAILURE', 'SINGLE_FAILURE', 'MIXED']) expect(blob).not.toContain(w)
  })
})

describe('validator rejects contract violations', () => {
  it('privileged field', () => {
    const r = clone(caseB) as unknown as Record<string, unknown>
    r._simulator_truth = { log_kd: -8 }
    expect(() => assertRecord(r)).toThrow(/privileged/)
  })
  it('scalar value / metadata on an observation', () => {
    const r = clone(caseB)
    ;(r.events[0].observation as unknown as Record<string, unknown>).value = 1
    expect(() => assertRecord(r)).toThrow(/scalar value/)
  })
  it('empty measurements', () => {
    const r = clone(caseB)
    r.events[0].observation!.measurements = {}
    expect(() => assertRecord(r)).toThrow(/non-empty/)
  })
  it('non-contiguous steps', () => {
    const r = clone(caseB)
    r.events[2].step = 9
    expect(() => assertRecord(r)).toThrow(/non-contiguous/)
  })
  it('resource accounting gap', () => {
    const r = clone(caseB)
    r.events[1].resources_before.budget_remaining += 1
    expect(() => assertRecord(r)).toThrow(/accounting/)
  })
  it('probability outside [0,1]', () => {
    const r = clone(caseB)
    r.events[0].belief_after.p_kinetic_failure = 1.2
    expect(() => assertRecord(r)).toThrow(/probability/)
  })
  it('redesign without a new candidate', () => {
    const r = clone(caseAMirage)
    delete (r.events[1] as { active_candidate_after?: unknown }).active_candidate_after
    expect(() => assertRecord(r)).toThrow(/active_candidate_after/)
  })
  it('comparison must share one seed', () => {
    const c = clone(comparisonCase1)
    c.records[1].seed = 1
    expect(() => assertComparison(c)).toThrow(/seed/)
  })
})

describe('projection', () => {
  const frames = projectEpisode(caseAMirage)

  it('yields one frame per event plus the initial state, with contiguous steps', () => {
    expect(frames).toHaveLength(caseAMirage.events.length + 1)
    frames.forEach((f, i) => expect(f.step).toBe(i))
    expect(frames[0].status).toBe('running')
    expect(frames.at(-1)!.status).toBe('terminal')
  })

  it("frame i's recommendation is the action event i+1 executes; none when terminal", () => {
    frames.slice(0, -1).forEach((f, i) => expect(f.recommendation!.action_type).toBe(caseAMirage.events[i].action.action_type))
    expect(frames.at(-1)!.recommendation).toBeNull()
  })

  it('belief marginals are independent (may sum above 1) and entropy falls over the episode', () => {
    expect(MECHANISMS.reduce((a, m) => a + frames[1].belief.p[m], 0)).toBeGreaterThan(1)
    expect(frames.at(-1)!.belief.entropy).toBeLessThan(frames[0].belief.entropy)
  })

  it('support / contradiction is derived from belief change', () => {
    const sec = frames[1].events[1]
    expect(sec.links.find((l) => l.mechanism === 'aggregation')!.relation).toBe('supports')
    const sec2 = frames[3].events[3]
    expect(sec2.links.find((l) => l.mechanism === 'aggregation')!.relation).toBe('contradicts')
    const spr = frames[4].events[4]
    expect(spr.links.find((l) => l.mechanism === 'kinetic')!.relation).toBe('supports')
  })

  it('poor-quality readings are unresolved, not evidence', () => {
    const g = projectEpisode(caseAGreedy)
    const spr = g[1].events[1]
    expect(spr.observation!.quality).toBe('degraded')
    expect(spr.links.every((l) => l.relation === 'unresolved' || !['affinity', 'kinetic', 'aggregation'].includes(l.mechanism))).toBe(true)
  })

  it('lineage follows redesigns and the terminal decision marks the selected candidate', () => {
    expect(frames.at(-1)!.lineage.map((l) => [l.id, l.generation, l.parent_id])).toEqual([
      ['MB-0417', 0, null],
      ['MB-0417-g1', 1, 'MB-0417'],
      ['MB-0417-g2', 2, 'MB-0417-g1'],
    ])
    expect(frames.at(-1)!.candidate.status).toBe('selected')
    expect(frames[2].candidate.id).toBe('MB-0417-g1')
  })

  it('actual cost and SPR damage come from resource accounting', () => {
    const g = projectEpisode(caseAGreedy)
    expect(g[1].events[1].cost).toEqual({ budget: 640, sample: 40, time: 6 })
    expect(g[1].events[1].spr_delta).toBeCloseTo(-0.65, 5)
    expect(projectEpisode(caseAMirage).every((f) => f.resources.spr_health > 0.9)).toBe(true)
  })

  it('evaluation is attached only to the terminal frame', () => {
    expect(frames.slice(0, -1).every((f) => f.terminal === null)).toBe(true)
    expect(frames.at(-1)!.terminal!.evaluation!.justified).toBe(true)
  })

  it('assay case: no redesign, assay invalid becomes leading', () => {
    const b = projectEpisode(caseB)
    expect(b.at(-1)!.events.some((e) => e.kind === 'redesign')).toBe(false)
    expect(mechanismStatus(b[1].belief.p.assay_invalid)).toBe('active')
    expect(b.at(-1)!.candidate.id).toBe('MB-0231')
  })

  it('graph has 8 mechanism nodes and all three relation types in the compound case', () => {
    const g = buildGraph(frames[4])
    expect(g.nodes.filter((n) => n.kind === 'mechanism')).toHaveLength(8)
    for (const rel of ['supports', 'contradicts', 'unresolved', 'targets']) expect(g.edges.some((e) => e.relation === rel)).toBe(true)
  })

  it('beliefRows deltas and timeline', () => {
    expect(beliefRows(frames[1], frames[0]).find((r) => r.mechanism === 'aggregation')!.delta).toBeCloseTo(0.49, 5)
    expect(timelineItems(frames).map((t) => t.kind)).toEqual(['failure', 'measurement', 'redesign', 'measurement', 'measurement', 'measurement', 'redesign', 'measurement', 'decision'])
  })

  it('deriveLinks ignores sub-threshold movement on uninformed mechanisms', () => {
    const b = toBelief(caseB.initial_state.belief)
    expect(deriveLinks(b, b, [], 'good')).toEqual([])
  })
})

describe('policy comparison and counterfactual', () => {
  const cmp = projectComparison(comparisonCase1)
  it('identical seeded world; policies diverge at step 0', () => {
    expect(new Set(cmp.tracks.map((t) => t.frames[0].seed)).size).toBe(1)
    expect(divergenceStep(cmp.tracks)).toBe(0)
    const rec = (n: string) => cmp.tracks.find((t) => t.policy.name === n)!.frames[0].recommendation!.action_type
    expect(rec('GreedyEIGPolicy')).toBe('MEASURE_SPR')
    expect(rec('PPOPolicy')).toBe('MEASURE_SEC')
  })
  it('counterfactual from the other branch shows SPR damage; none after policies stop sharing history', () => {
    const cf = counterfactualFor(cmp, 'PPOPolicy', 0)!
    expect(cf.alternative.action).toBe('MEASURE_SPR')
    expect(cf.simulated).toBe(true)
    expect(cf.consequences.some((c) => c.kind === 'instrument' && c.severity === 'bad')).toBe(true)
    expect(counterfactualFor(cmp, 'PPOPolicy', 3)).toBeNull()
    expect(counterfactualFor(null, 'PPOPolicy', 0)).toBeNull()
  })
})

describe('ReplayTransport over the mock source', () => {
  it('lists, opens, compares, reports benchmark; refuses to step', async () => {
    const t = new ReplayTransport(mockSource, { kind: 'mock' })
    expect((await t.listEpisodes()).length).toBe(3)
    const s = await t.openEpisode(caseAMirage.scenario.id)
    expect(s.mode).toBe('replay')
    expect(s.record.policy.name).toBe('PPOPolicy')
    expect((await t.openEpisode(caseAMirage.scenario.id, 'GreedyEIGPolicy')).record.policy.name).toBe('GreedyEIGPolicy')
    expect(await t.getPolicyComparison(caseAMirage.scenario.id)).not.toBeNull()
    expect(await t.getPolicyComparison(caseB.scenario.id)).toBeNull()
    expect((await t.getBenchmark()).status).toBe('mock')
    await expect(t.step()).rejects.toThrow()
    await expect(t.openEpisode('nope')).rejects.toThrow()
  })
})

describe('LiveApiTransport (fake fetch, no backend)', () => {
  const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))

  it('opens a record, posts the recommended action, validates, and maps 404 benchmark to NOT RUN', async () => {
    const partial = clone(caseB)
    const open = { ...partial, events: partial.events.slice(0, 1), terminal_decision: null, complete: false, pending: { recommendation: { action: partial.events[1].action } } }
    const next = { ...partial, events: partial.events.slice(0, 2), terminal_decision: null, complete: false }
    const calls: string[] = []
    const t = new LiveApiTransport('/api', ((url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (url.endsWith('/episodes') && init?.method === 'POST') return json({ session_id: 's1', mode: 'live', record: open })
      if (url.endsWith('/episodes/s1/actions')) {
        expect(JSON.parse(init!.body as string).action_type).toBe('MEASURE_SPR')
        return json({ session_id: 's1', mode: 'live', record: next })
      }
      if (url.endsWith('/benchmark')) return json({}, 404)
      return json({}, 500)
    }) as typeof fetch)
    const s = await t.openEpisode('x')
    expect(s.mode).toBe('live')
    expect(projectEpisode(s.record)).toHaveLength(2)
    expect(projectEpisode(s.record).at(-1)!.recommendation!.action_type).toBe('MEASURE_SPR')
    const s2 = await t.step('s1')
    expect(s2.record.events).toHaveLength(2)
    expect((await t.getBenchmark()).status).toBe('not_run')
    expect(calls.length).toBe(2)
  })

  it('rejects a payload that leaks privileged fields', async () => {
    const bad = { ...clone(caseB), _privileged_state: { assay_validity: false } }
    const t = new LiveApiTransport('/api', (() => json({ session_id: 's', mode: 'live', record: bad })) as typeof fetch)
    await expect(t.openEpisode('x')).rejects.toThrow(/privileged/)
  })

  it('surfaces network failure as a TransportError with the URL', async () => {
    const t = new LiveApiTransport('/api', (() => Promise.reject(new Error('ECONNREFUSED'))) as typeof fetch)
    await expect(t.listEpisodes()).rejects.toThrow(/Cannot reach backend at \/api\/health/)
  })
})

describe('benchmark', () => {
  const rep = adaptBenchmark(mockBenchmark)
  it('is flagged mock and exercises not_run / na states', () => {
    expect(rep.status).toBe('mock')
    const flat = Object.values(rep.cells).flatMap((f) => Object.values(f).flatMap((p) => Object.values(p)))
    expect(flat.some((c) => c.status === 'not_run')).toBe(true)
    expect(flat.some((c) => c.status === 'na')).toBe(true)
  })
  it('all-worlds aggregate excludes slices and reports coverage; never fabricates a missing cell', () => {
    const a = aggregateCell(rep, ALL_FAMILIES, 'PPOPolicy', 'terminal_correct')
    expect(a.total).toBe(rep.families.filter((f) => !f.slice).length)
    expect(a.of).toBe(a.total - 1) // PPO not run on one family
    expect(aggregateCell(rep, ALL_FAMILIES, 'PPOPolicy', 'proxy_exploitation').cell.status).toBe('not_run')
    expect(aggregateCell(rep, 'MODEL_FAILURE', 'PPOPolicy', 'terminal_correct').cell.status).toBe('not_run')
  })
})
