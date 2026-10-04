import { describe, expect, it } from 'vitest'
import { LiveApiTransport } from './liveApiTransport'
import { projectEpisode } from './project'

/**
 * REAL BACKEND. No fake fetch. Skipped unless MIRAGE_API_URL points at a running H0 server:
 *
 *   MIRAGE_API_URL=http://localhost:8100 MIRAGE_EVAL_TOKEN=... npm test
 *
 * Needs the policies `rescue_planner` and `greedy_eig` registered (H0's own service registers only
 * random / fixed_pipeline; see fixtures/README.md). MIRAGE_EVAL_TOKEN is optional: with it, the
 * per-episode verdict route is exercised too.
 */
const API = process.env.MIRAGE_API_URL
const TOKEN = process.env.MIRAGE_EVAL_TOKEN

// Node's fetch needs absolute URLs; the app uses same-origin /api through the dev proxy.
const realFetch: typeof fetch = (input, init) => {
  const headers = new Headers(init?.headers)
  if (TOKEN && String(input).includes('/benchmarks')) headers.set('X-Mirage-Eval-Token', TOKEN)
  return fetch(`${API}${String(input).replace(/^\/api/, '')}`, { ...init, headers })
}

describe.skipIf(!API)('LiveApiTransport against the REAL H0 backend', () => {
  const make = () => new LiveApiTransport({ seeds: [9], evaluation: Boolean(TOKEN), benchmarks: false }, realFetch)

  it('plays a RECEPTOR_BINDER_RESCUE campaign end to end through the public API', async () => {
    const t = make()
    let s = await t.openEpisode('seed-9', 'rescue_planner')
    expect(s.record.campaign).toBe('RECEPTOR_BINDER_RESCUE')
    expect(s.record.pending?.recommendation?.action.action_type).toBe('MEASURE_SEC')
    expect(projectEpisode(s.record)[0].belief.p.aggregation).toBeGreaterThan(0)

    const seen: string[] = []
    for (let i = 0; i < 20 && !s.record.complete; i++) {
      s = await t.step(s.session_id)
      seen.push(s.record.events.at(-1)!.action.action_type)
    }
    expect(seen.slice(0, 3)).toEqual(['MEASURE_SEC', 'REDESIGN_SOLUBILITY', 'MEASURE_SPR'])
    const frames = projectEpisode(s.record)
    const last = frames.at(-1)!
    expect(last.status).toBe('terminal')
    expect(last.lineage.length).toBe(2)
    expect(last.resources.spr_health).toBe(1)
    // structured, multi-measurement observations
    const spr = last.events.find((e) => e.action_type === 'MEASURE_SPR')!.observation!
    expect(spr.measurements.map((m) => m.name).sort()).toEqual(['log_kd', 'log_koff'])
    // beliefs update, and are independent marginals
    expect(frames[1].belief.p.aggregation).not.toBe(frames[0].belief.p.aggregation)
    if (TOKEN) expect(last.terminal!.evaluation).not.toBeNull()
  })

  it('greedy EIG on the same seed damages the SPR instrument', async () => {
    const t = make()
    let s = await t.openEpisode('seed-9', 'greedy_eig')
    expect(s.record.pending?.recommendation?.action.action_type).toBe('MEASURE_SPR')
    s = await t.step(s.session_id)
    const f = projectEpisode(s.record).at(-1)!
    expect(f.events.at(-1)!.observation!.quality).toBe('degraded')
    expect(f.resources.spr_health).toBeLessThan(1)
  })

  it('same-seed comparison returns real lanes and NOT RUN for unregistered policies', async () => {
    const cmp = (await make().getPolicyComparison('seed-9'))!
    expect(cmp.tracks.length).toBeGreaterThanOrEqual(2)
    expect(cmp.tracks.every((x) => x.provenance.source === 'live')).toBe(true)
    expect(cmp.not_run.map((n) => n.policy.name)).toEqual(expect.arrayContaining(['lookahead', 'ppo']))
  })

  it('an unregistered policy is rejected by the server as NOT RUN', async () => {
    await expect(make().openEpisode('seed-9', 'ppo')).rejects.toThrow(/NOT RUN/)
  })
})
