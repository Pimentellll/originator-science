import { describe, expect, it } from 'vitest'
import rescueReplay from './fixtures/replay-rescue_planner-9.json'
import stateFx from './fixtures/state-9.json'
import { LiveApiTransport } from './liveApiTransport'
import { parseEnvironment, recordFromReplay } from './fromApi'
import { launchFromSearch } from '../state/launch'
import { GUIDED_PRESET } from '../state/sessionContext'
import type { ApiReplay } from './api'

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
const replay = rescueReplay as unknown as ApiReplay

const POLICIES = [
  { name: 'rescue_planner', display_name: 'Rescue Planner', kind: 'domain_expert', available: true, description: 'd', reason: null },
  { name: 'random', display_name: 'Random', kind: 'random', available: true, description: 'd', reason: null },
  { name: 'ppo', display_name: 'PPO', kind: 'learned_policy', available: false, description: 'd', reason: 'not wired' },
]

function server() {
  const posts: unknown[] = []
  const actions: unknown[] = []
  const handler = ((url: string, init?: RequestInit) => {
    const path = url.replace(/^\/api/, '')
    if (path === '/health') return json({ status: 'ok', version: 'mirage.api/1' })
    if (path === '/policies') return json(POLICIES)
    if (path === '/scenarios') return json([{ id: 'broken_assay', title: 'Broken assay', summary: 's', cli_name: 'ASSAY_FAILURE', is_default: false }])
    if (path === '/version') return json({ mirage_version: '0.1.0', git_sha: 'abc', git_dirty: false, commit_date: null, api_version: 'mirage.api/1', contract_version: 'c', scenario_semantics_default: 'SEMANTICS_V2', scenario_semantics_available: ['BASELINE_V1', 'SEMANTICS_V2'], python_version: '3.12' })
    if (path === '/episodes' && init?.method === 'POST') {
      posts.push(JSON.parse(init.body as string))
      return json({ ...stateFx, episode_id: 'ep-1', available_actions: [{ action_type: 'MEASURE_SEC', candidate_id: 'binder-000' }, { action_type: 'REJECT', candidate_id: 'binder-000' }] }, 201)
    }
    if (path === '/episodes/ep-1/replay') return json({ ...replay, episode_id: 'ep-1', events: [], complete: false, terminal_decision: null, environment_id: 'RECEPTOR_BINDER_RESCUE/SEMANTICS_V2' })
    if (path === '/episodes/ep-1/recommendation') return json({ episode_id: 'ep-1', policy_name: 'rescue_planner', action: replay.events[0].action })
    if (path === '/episodes/ep-1/actions' && init?.method === 'POST') {
      actions.push(JSON.parse(init.body as string))
      return json({ event: { ...replay.events[0], episode_id: 'ep-1' }, state: { ...stateFx, episode_id: 'ep-1', terminal: false, available_actions: [{ action_type: 'MEASURE_SPR', candidate_id: 'binder-000' }] } })
    }
    return json({ detail: 'nf' }, 404)
  }) as unknown as typeof fetch
  return { handler, posts, actions }
}

describe('launch choices from the URL', () => {
  it('defaults to the server scenario, seed 9, auto policy, not guided', () => {
    expect(launchFromSearch('?transport=live')).toEqual({ scenario: null, semantics: null, policy: null, seed: 9, control: 'auto', guided: false })
  })
  it('guided=1 is the deterministic preset', () => {
    expect(launchFromSearch('?guided=1')).toEqual({ ...GUIDED_PRESET, guided: true })
  })
  it('reads what ./mirage demo passes, and refuses anything that is not a plain identifier', () => {
    const c = launchFromSearch('?seed=4&scenario=ASSAY_FAILURE&semantics=BASELINE_V1&policy=greedy_eig&control=manual')
    expect(c).toMatchObject({ seed: 4, scenario: 'ASSAY_FAILURE', semantics: 'BASELINE_V1', policy: 'greedy_eig', control: 'manual' })
    expect(launchFromSearch('?scenario=../../etc&seed=-1&policy=a b').scenario).toBeNull()
    expect(launchFromSearch('?seed=-1').seed).toBe(9)
  })
})

describe('environment_id parsing never surfaces a world', () => {
  it('accepts the profile and a known semantics version', () => {
    expect(parseEnvironment('RECEPTOR_BINDER_RESCUE/SEMANTICS_V2')).toEqual({ campaign: 'RECEPTOR_BINDER_RESCUE', semantics: 'SEMANTICS_V2' })
    expect(parseEnvironment('RECEPTOR_BINDER_RESCUE')).toEqual({ campaign: 'RECEPTOR_BINDER_RESCUE' })
  })
  it('drops anything unknown, including a world name in either position', () => {
    expect(parseEnvironment('binder:secret_world')).toEqual({})
    expect(parseEnvironment('RECEPTOR_BINDER_RESCUE/COMPOUND_FAILURE')).toEqual({ campaign: 'RECEPTOR_BINDER_RESCUE' })
  })
  it('the record carries the semantics version', () => {
    const rec = recordFromReplay({ ...replay, environment_id: 'RECEPTOR_BINDER_RESCUE/BASELINE_V1' })
    expect(rec.semantics).toBe('BASELINE_V1')
  })
})

describe('LiveApiTransport catalogue, scenario selection and manual actions', () => {
  it('offers only the policies /policies marks available, and sends scenario + semantics with the reset', async () => {
    const s = server()
    const t = new LiveApiTransport({ policies: ['should', 'be', 'ignored'] }, s.handler)
    const eps = await t.listEpisodes()
    expect(eps.map((e) => e.policy.name)).toEqual(['rescue_planner', 'random'])
    await t.openEpisode('seed-9', 'rescue_planner', { scenario: 'broken_assay', semantics: 'BASELINE_V1' })
    expect(s.posts[0]).toEqual({ seed: 9, policy_name: 'rescue_planner', scenario: 'broken_assay', scenario_version: 'BASELINE_V1' })
  })

  it('omits scenario fields when none were chosen, so the server default applies', async () => {
    const s = server()
    await new LiveApiTransport({}, s.handler).openEpisode('seed-9', 'rescue_planner')
    expect(s.posts[0]).toEqual({ seed: 9, policy_name: 'rescue_planner' })
  })

  it('manual act: only actions the public state allows, and the choice is what is executed', async () => {
    const s = server()
    const t = new LiveApiTransport({}, s.handler)
    const open = await t.openEpisode('seed-9', 'rescue_planner')
    expect(open.available_actions).toEqual(['MEASURE_SEC', 'REJECT'])
    await expect(t.act!(open.session_id, 'MEASURE_SPR')).rejects.toThrow(/not available in the current public state/)
    const next = await t.act!(open.session_id, 'REJECT')
    expect(s.actions[0]).toMatchObject({ action_type: 'REJECT', rationale: 'manual scientist' })
    expect(next.available_actions).toEqual(['MEASURE_SPR'])
  })

  it('catalogue tolerates a server without the new routes', async () => {
    const old = new LiveApiTransport({}, (() => json({ detail: 'nf' }, 404)) as unknown as typeof fetch)
    expect(await old.catalogue!()).toEqual({ version: null, policies: null, scenarios: null })
  })

  it('diagnostics reports an unreachable API as a failed check, not a crash', async () => {
    const down = new LiveApiTransport({}, (() => Promise.reject(new Error('ECONNREFUSED'))) as unknown as typeof fetch)
    const r = await down.diagnostics!()
    expect(r.reachable).toBe(false)
    expect(r.checks[0]).toMatchObject({ name: 'API reachable', status: 'fail' })
  })
})
