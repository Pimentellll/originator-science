import { describe, expect, it } from 'vitest'
import rescueReplay from './fixtures/replay-rescue_planner-9.json'
import greedyReplay from './fixtures/replay-greedy_eig-9.json'
import fixedReplay from './fixtures/replay-fixed_pipeline-9.json'
import randomReplay from './fixtures/replay-random-9.json'
import emptyReplay from './fixtures/replay-empty-9.json'
import stateFx from './fixtures/state-9.json'
import recFx from './fixtures/recommendation-rescue_planner-9.json'
import evRescue from './fixtures/evaluation-rescue_planner-9.json'
import evGreedy from './fixtures/evaluation-greedy_eig-9.json'
import evFixed from './fixtures/evaluation-fixed_pipeline-9.json'
import evRandom from './fixtures/evaluation-random-9.json'
import summaryFx from './fixtures/benchmark-summary.schema-fixture.json'
import { LiveApiTransport } from './liveApiTransport'
import { projectEpisode } from './project'
import { assertRecord } from './validate'
import { recordFromReplay } from './fromApi'
import { aggregateCell, ALL_FAMILIES } from './derive'
import type { ApiEpisodeEvaluation, ApiReplay } from './api'

/**
 * These tests drive LiveApiTransport through a fake server that replays REAL captured H0 output
 * (fixtures/README.md), so the adapters are checked against the genuine wire shapes: 0-based
 * steps, nullable beliefs, child_candidate_id, spr_instrument_health, RECEPTOR_BINDER_RESCUE.
 * The no-fake-fetch version of this suite is live.integration.test.ts.
 */
const REPLAYS: Record<string, ApiReplay> = {
  rescue_planner: rescueReplay as unknown as ApiReplay,
  greedy_eig: greedyReplay as unknown as ApiReplay,
  fixed_pipeline: fixedReplay as unknown as ApiReplay,
  random: randomReplay as unknown as ApiReplay,
}
const EVALS: Record<string, ApiEpisodeEvaluation> = {
  rescue_planner: evRescue as unknown as ApiEpisodeEvaluation,
  greedy_eig: evGreedy as unknown as ApiEpisodeEvaluation,
  fixed_pipeline: evFixed as unknown as ApiEpisodeEvaluation,
  random: evRandom as unknown as ApiEpisodeEvaluation,
}

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))

function fakeApi(opts: { benchmarks?: 'off' | 'empty' | 'summary'; evaluation?: boolean; policyErrors?: Record<string, number> } = {}) {
  const eps = new Map<string, { policy: string; i: number }>()
  const calls: string[] = []
  let n = 0
  const handler = ((url: string, init?: RequestInit) => {
    const path = url.replace(/^\/api/, '')
    const method = init?.method ?? 'GET'
    calls.push(`${method} ${path}`)
    if (path === '/health') return json({ status: 'ok', version: 'mirage.api/1' })
    if (path === '/episodes' && method === 'POST') {
      const policy = JSON.parse(init!.body as string).policy_name as string
      const errorStatus = opts.policyErrors?.[policy]
      if (errorStatus) return json({ detail: errorStatus === 422 ? 'unknown policy' : 'server error' }, errorStatus)
      if (!REPLAYS[policy]) return json({ detail: 'unknown policy' }, 422)
      const id = `ep-${++n}`
      eps.set(id, { policy, i: 0 })
      return json({ ...stateFx, episode_id: id }, 201)
    }
    const ev = /^\/benchmarks\/episodes\/([^/]+)$/.exec(path)
    if (ev) {
      const ep = eps.get(ev[1])
      if (!opts.evaluation) return json({ detail: 'aggregate results are not enabled' }, 404)
      return ep && ep.i >= REPLAYS[ep.policy].events.length ? json(EVALS[ep.policy]) : json({ detail: 'evaluation is available only after the episode is terminal' }, 409)
    }
    const m = /^\/episodes\/([^/]+)(\/.*)?$/.exec(path)
    if (m) {
      const ep = eps.get(m[1])
      if (!ep) return json({ detail: 'episode not found' }, 404)
      const r = REPLAYS[ep.policy]
      const tail = m[2] ?? ''
      if (tail === '/recommendation') return ep.i >= r.events.length ? json({ detail: 'episode already terminal' }, 409) : json({ episode_id: m[1], policy_name: ep.policy, action: r.events[ep.i].action })
      if (tail === '/actions' && method === 'POST') {
        const body = JSON.parse(init!.body as string)
        expect(body.action_type).toBe(r.events[ep.i].action.action_type)
        const event = { ...r.events[ep.i], episode_id: m[1] }
        ep.i++
        return json({ event, state: { ...stateFx, episode_id: m[1], terminal: ep.i >= r.events.length } })
      }
      if (tail === '/replay') {
        const done = ep.i >= r.events.length
        const base = ep.i === 0 ? { ...r, events: [] } : r
        return json({ ...base, episode_id: m[1], events: r.events.slice(0, ep.i).map((e) => ({ ...e, episode_id: m[1] })), complete: done, terminal_decision: done ? r.terminal_decision : null })
      }
      return json({ ...stateFx, episode_id: m[1] })
    }
    if (path === '/benchmarks') {
      if (opts.benchmarks === 'summary') return json(['schema-fixture'])
      if (opts.benchmarks === 'empty') return json([])
      return json({ detail: 'aggregate results are not enabled' }, 404)
    }
    if (path === '/benchmarks/schema-fixture') return json(summaryFx)
    return json({ detail: 'not found' }, 404)
  }) as unknown as typeof fetch
  return { handler, calls }
}

describe('real H0 fixtures', () => {
  it('convert to valid normalised records (steps renumbered from 1) with the RECEPTOR_BINDER_RESCUE campaign', () => {
    for (const r of Object.values(REPLAYS)) {
      const rec = recordFromReplay(r)
      expect(() => assertRecord(JSON.parse(JSON.stringify(rec)))).not.toThrow()
      rec.events.forEach((e, i) => expect(e.step).toBe(i + 1))
      expect(rec.campaign).toBe('RECEPTOR_BINDER_RESCUE')
    }
    expect(() => recordFromReplay(emptyReplay as unknown as ApiReplay, { initial: stateFx as never })).not.toThrow()
  })

  it('rescue planner: SEC, then solubility redesign (lineage grows), then SPR on a healthy instrument', () => {
    const frames = projectEpisode(recordFromReplay(REPLAYS.rescue_planner))
    expect(REPLAYS.rescue_planner.events.map((e) => e.action.action_type).slice(0, 3)).toEqual(['MEASURE_SEC', 'REDESIGN_SOLUBILITY', 'MEASURE_SPR'])
    const last = frames.at(-1)!
    expect(last.lineage.length).toBe(2)
    expect(last.lineage[1].parent_id).toBe(last.lineage[0].id)
    expect(last.lineage[1].generation).toBe(1)
    expect(last.lineage[1].created_by).toBe('REDESIGN_SOLUBILITY')
    expect(last.resources.spr_health).toBe(1)
    const sec = frames[1].events[1].observation!
    expect(sec.measurements.map((m) => m.name)).toEqual(['monomer_fraction'])
  })

  it('greedy EIG on the real backend: premature SPR degrades the instrument and the reading is flagged degraded', () => {
    const frames = projectEpisode(recordFromReplay(REPLAYS.greedy_eig))
    expect(frames[0].recommendation!.action_type).toBe('MEASURE_SPR')
    const spr = frames[1].events[1]
    expect(spr.observation!.quality).toBe('degraded')
    expect(spr.observation!.measurements.map((m) => m.name).sort()).toEqual(['log_kd', 'log_koff'])
    expect(spr.spr_delta).toBeLessThan(-0.05)
    expect(frames.at(-1)!.resources.spr_health).toBeLessThan(1)
  })

  it('the verdict separates CORRECT from JUSTIFIED: greedy EIG is lucky-correct, the rescue planner is justified', () => {
    const verdict = (p: string) => projectEpisode(recordFromReplay(REPLAYS[p], { evaluation: EVALS[p] })).at(-1)!.terminal!.evaluation!
    expect(verdict('greedy_eig')).toMatchObject({ terminal_correct: true, justified: false, lucky_correct: true })
    expect(verdict('rescue_planner')).toMatchObject({ terminal_correct: true, justified: true, lucky_correct: false })
    expect(verdict('rescue_planner').checks!.length).toBeGreaterThan(0)
    // never attached before the terminal frame
    const frames = projectEpisode(recordFromReplay(REPLAYS.rescue_planner, { evaluation: EVALS.rescue_planner }))
    expect(frames.slice(0, -1).every((f) => f.terminal === null)).toBe(true)
  })

  it('does not surface a world-named environment_id', () => {
    const rec = recordFromReplay({ ...REPLAYS.greedy_eig, environment_id: 'binder:secret_world' })
    expect(rec.campaign).toBeUndefined()
    expect(JSON.stringify(projectEpisode(rec))).not.toContain('secret_world')
  })

  it('a leaking payload is refused', () => {
    const bad = { ...recordFromReplay(REPLAYS.greedy_eig), _simulator_truth: { log_kd: -8 } }
    expect(() => assertRecord(JSON.parse(JSON.stringify(bad)))).toThrow(/privileged/)
  })
})

describe('LiveApiTransport against a fake server serving real captured output', () => {
  it('lists seed scenarios x configured policies after a health check', async () => {
    const { handler, calls } = fakeApi()
    const eps = await new LiveApiTransport({ seeds: [9] }, handler).listEpisodes()
    expect(calls[0]).toBe('GET /health')
    expect(eps.map((e) => e.policy.label)).toEqual(['RESCUE PLANNER', 'GREEDY EIG', 'FIXED PIPELINE', 'RANDOM'])
  })

  it('reset -> recommendation -> executes the recommended action -> terminal, with the verdict when configured', async () => {
    const { handler, calls } = fakeApi({ evaluation: true })
    const t = new LiveApiTransport({ evaluation: true }, handler)
    let s = await t.openEpisode('seed-9', 'rescue_planner')
    expect(s.mode).toBe('live')
    expect(s.record.events).toHaveLength(0)
    expect(s.record.campaign).toBe('RECEPTOR_BINDER_RESCUE')
    expect(s.record.pending?.recommendation?.action.action_type).toBe(recFx.action.action_type)
    expect(projectEpisode(s.record)).toHaveLength(1)

    const total = REPLAYS.rescue_planner.events.length
    for (let i = 0; i < total; i++) s = await t.step(s.session_id)
    expect(s.record.complete).toBe(true)
    const frames = projectEpisode(s.record)
    expect(frames.at(-1)!.status).toBe('terminal')
    expect(frames.at(-1)!.terminal!.evaluation).toMatchObject({ terminal_correct: true, justified: true })
    expect(calls.filter((c) => c.endsWith('/actions')).length).toBe(total)
    await expect(t.step(s.session_id)).rejects.toThrow(/no recommended action/)
  })

  it('no verdict is requested unless configured, and a refusal means "none attached", not an error', async () => {
    const quiet = fakeApi({ evaluation: true })
    const t = new LiveApiTransport({}, quiet.handler)
    let s = await t.openEpisode('seed-9', 'greedy_eig')
    for (let i = 0; i < REPLAYS.greedy_eig.events.length; i++) s = await t.step(s.session_id)
    expect(quiet.calls.some((c) => c.includes('/benchmarks/episodes/'))).toBe(false)
    expect(projectEpisode(s.record).at(-1)!.terminal!.evaluation).toBeNull()

    const off = new LiveApiTransport({ evaluation: true }, fakeApi({ evaluation: false }).handler)
    let o = await off.openEpisode('seed-9', 'greedy_eig')
    for (let i = 0; i < REPLAYS.greedy_eig.events.length; i++) o = await off.step(o.session_id)
    expect(projectEpisode(o.record).at(-1)!.terminal!.evaluation).toBeNull()
  })

  it('maps an unknown policy (HTTP 422) to a clear NOT RUN error', async () => {
    const t = new LiveApiTransport({}, fakeApi().handler)
    await expect(t.openEpisode('seed-9', 'ppo')).rejects.toThrow(/not available on this server: NOT RUN/)
  })

  it('same-seed comparison: real lanes for configured policies, NOT RUN for Lookahead and PPO, without probing', async () => {
    const api = fakeApi({ evaluation: true })
    const policies = ['rescue_planner', 'greedy_eig', 'fixed_pipeline', 'random']
    const cmp = (await new LiveApiTransport({ evaluation: true, policies }, api.handler).getPolicyComparison('seed-9'))!
    expect(cmp.tracks.map((x) => x.policy.name).sort()).toEqual(['fixed_pipeline', 'greedy_eig', 'random', 'rescue_planner'])
    expect(cmp.tracks.every((x) => x.provenance.source === 'live')).toBe(true)
    expect(new Set(cmp.tracks.map((x) => x.frames[0].seed))).toEqual(new Set([9]))
    expect(cmp.not_run.map((n) => n.policy.name).sort()).toEqual(['lookahead', 'ppo'])
    expect(api.calls.some((c) => c.includes('ppo') || c.includes('lookahead'))).toBe(false)
    const end = (n: string) => cmp.tracks.find((x) => x.policy.name === n)!.frames.at(-1)!
    expect(end('greedy_eig').resources.spr_health).toBeLessThan(end('rescue_planner').resources.spr_health)
    expect(end('greedy_eig').terminal!.evaluation).toMatchObject({ justified: false, lucky_correct: true })
  })

  it('keeps available comparison lanes and reports a configured 422 policy exactly once as NOT RUN', async () => {
    const api = fakeApi({ policyErrors: { lookahead: 422 } })
    const policies = ['rescue_planner', 'lookahead', 'fixed_pipeline', 'random']
    const cmp = (await new LiveApiTransport({ policies }, api.handler).getPolicyComparison('seed-9'))!
    expect(cmp.tracks).toHaveLength(3)
    expect(cmp.tracks.map((track) => track.policy.name).sort()).toEqual(['fixed_pipeline', 'random', 'rescue_planner'])
    const skipped = cmp.not_run.filter((entry) => entry.policy.name === 'lookahead')
    expect(skipped).toHaveLength(1)
    expect(skipped[0].reason).toBe('Not served by this server (POST /episodes answered 422 unknown policy).')
  })

  it('propagates non-422 errors from a configured comparison policy', async () => {
    const api = fakeApi({ policyErrors: { rescue_planner: 500 } })
    const t = new LiveApiTransport({ policies: ['rescue_planner', 'fixed_pipeline', 'random'] }, api.handler)
    await expect(t.getPolicyComparison('seed-9')).rejects.toMatchObject({ status: 500 })
  })

  it('benchmarks: not configured => NOT RUN with no request; 404 => NOT RUN; a real summary => real report', async () => {
    const quiet = fakeApi()
    const notConfigured = await new LiveApiTransport({}, quiet.handler).getBenchmark()
    expect(notConfigured.status).toBe('not_run')
    expect(notConfigured.provenance.label).toContain('./mirage benchmark-dev')
    expect(quiet.calls).toEqual([])
    const off = await new LiveApiTransport({ benchmarks: true }, fakeApi().handler).getBenchmark()
    expect(off.status).toBe('not_run')
    expect(off.provenance.label).toContain('./mirage demo')
    const empty = await new LiveApiTransport({ benchmarks: true }, fakeApi({ benchmarks: 'empty' }).handler).getBenchmark()
    expect(empty.status).toBe('not_run')
    expect(empty.provenance.label).toContain('hasn\'t been generated yet')
    expect(empty.provenance.label).toContain('./mirage demo')
    expect(empty.provenance.label).toContain('30 seconds')
    expect(empty.provenance.label).toContain('./mirage benchmark-dev')
    const rep = await new LiveApiTransport({ benchmarks: true }, fakeApi({ benchmarks: 'summary' }).handler).getBenchmark()
    expect(rep.status).toBe('real')
    expect(rep.policies.map((p) => p.label)).toEqual(['RANDOM', 'FIXED PIPELINE', 'GREEDY EIG', 'RESCUE PLANNER', 'LOOKAHEAD', 'PPO'])
    expect(aggregateCell(rep, ALL_FAMILIES, 'ppo', 'correct').cell.status).toBe('not_run')
    expect(aggregateCell(rep, ALL_FAMILIES, 'greedy_eig', 'correct').cell.status).toBe('ok')
  })

  it('surfaces network failure with the URL, and API errors with the public detail', async () => {
    const down = new LiveApiTransport({}, (() => Promise.reject(new Error('ECONNREFUSED'))) as typeof fetch)
    await expect(down.listEpisodes()).rejects.toThrow(/Cannot reach the MIRAGE API at \/api\/health/)
    const t = new LiveApiTransport({}, (() => json({ detail: 'too many live episodes' }, 409)) as typeof fetch)
    await expect(t.openEpisode('seed-1')).rejects.toThrow(/too many live episodes/)
  })
})
