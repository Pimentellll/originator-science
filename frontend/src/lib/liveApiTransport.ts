import { assertPublic, assertRecord } from './validate'
import { notRunReport } from './project'
import { TransportError } from './transport'
import type { EpisodeSession, ScientificTransport } from './transport'
import type { BenchmarkReport, EpisodeSummary, PolicyComparison } from './types'
import type { EpisodeRecord, ScientificAction } from './wire'

type ApiState = {
  episode_id: string
  terminal: boolean
  active_candidate: EpisodeRecord['initial_state']['candidate']
  resources: EpisodeRecord['initial_state']['resources']
  belief: EpisodeRecord['initial_state']['belief'] | null
}

type ApiStep = { event: Omit<EpisodeRecord['events'][number], 'active_candidate_after'>; state: ApiState }
type ApiRecommendation = { action: ScientificAction }

const scenario = { id: 'receptor-binder-rescue', title: 'Receptor binder rescue', summary: 'Public causal-rescue campaign.' }

export class LiveApiTransport implements ScientificTransport {
  readonly kind = 'live' as const
  readonly label = 'LIVE API'
  private readonly base: string
  private readonly fetchImpl: typeof fetch
  private readonly sessions = new Map<string, EpisodeSession>()

  constructor(base = '/api', fetchImpl: typeof fetch = (...a) => fetch(...a)) {
    this.base = base.replace(/\/$/, '')
    this.fetchImpl = fetchImpl
  }

  private legacy(raw: unknown): EpisodeSession | null {
    if (!raw || typeof raw !== 'object' || !('session_id' in raw) || !('record' in raw)) return null
    const value = raw as { session_id: unknown; mode?: unknown; record: unknown }
    if (typeof value.session_id !== 'string') throw new TransportError('session: missing session_id')
    const session: EpisodeSession = { session_id: value.session_id, mode: value.mode === 'replay' ? 'replay' : 'live', record: assertRecord(value.record) }
    this.sessions.set(session.session_id, session)
    return session
  }

  private async request(path: string, init?: RequestInit): Promise<unknown> {
    let res: Response
    try {
      res = await this.fetchImpl(this.base + path, { ...init, headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...init?.headers } })
    } catch (e) {
      throw new TransportError('Cannot reach backend at ' + this.base + path + ': ' + (e instanceof Error ? e.message : String(e)))
    }
    if (!res.ok) throw new TransportError((init?.method ?? 'GET') + ' ' + path + ' -> ' + res.status + ' ' + res.statusText, res.status)
    const body = await res.json()
    assertPublic(body, 'api')
    return body
  }

  private record(state: ApiState, policyName: string, seed: number): EpisodeRecord {
    if (!state.belief) throw new TransportError('API state is missing public belief')
    return assertRecord({
      contract_version: 'mirage.core/1', episode_id: state.episode_id, seed, scenario, policy: { name: policyName },
      initial_state: { candidate: state.active_candidate, resources: state.resources, belief: state.belief, notes: [] },
      events: [], terminal_decision: null, provenance: { source: 'live', label: 'FastAPI public DTO' }, complete: state.terminal,
    })
  }

  private async recommend(session: EpisodeSession): Promise<EpisodeSession> {
    if (session.record.complete) return session
    const raw = await this.request('/episodes/' + encodeURIComponent(session.session_id) + '/recommendation') as ApiRecommendation
    const next = { ...session, record: assertRecord({ ...session.record, pending: { recommendation: { action: raw.action } } }) }
    this.sessions.set(next.session_id, next)
    return next
  }

  async listEpisodes(): Promise<EpisodeSummary[]> {
    await this.request('/health')
    return [{ episode_id: scenario.id, scenario, policy: { name: 'fixed_pipeline', label: 'Fixed pipeline' }, seed: 9, provenance: { source: 'live', label: 'FastAPI public DTO' } }]
  }

  async openEpisode(_scenarioId: string, policyName = 'fixed_pipeline'): Promise<EpisodeSession> {
    const seed = 9
    const raw = await this.request('/episodes', { method: 'POST', body: JSON.stringify({ seed, policy_name: policyName }) })
    const old = this.legacy(raw)
    if (old) return old
    const state = raw as ApiState
    const session: EpisodeSession = { session_id: state.episode_id, mode: 'live', record: this.record(state, policyName, seed) }
    this.sessions.set(session.session_id, session)
    return this.recommend(session)
  }

  async step(sessionId: string): Promise<EpisodeSession> {
    const current = this.sessions.get(sessionId)
    const action = current?.record.pending?.recommendation?.action
    if (!current || !action) throw new TransportError('No recommended action to execute for this session')
    const raw = await this.request('/episodes/' + encodeURIComponent(sessionId) + '/actions', { method: 'POST', body: JSON.stringify({ action_type: action.action_type, candidate_id: action.candidate_id }) })
    const old = this.legacy(raw)
    if (old) return old
    const step = raw as ApiStep
    const event = { ...step.event, step: step.event.step + 1, active_candidate_after: step.state.active_candidate }
    const record = assertRecord({ ...current.record, events: [...current.record.events, event], terminal_decision: step.state.terminal ? action : null, complete: step.state.terminal, pending: undefined })
    const next: EpisodeSession = { session_id: sessionId, mode: 'live', record }
    this.sessions.set(sessionId, next)
    return this.recommend(next)
  }

  async getPolicyComparison(_scenarioId: string): Promise<PolicyComparison | null> {
    return null
  }

  async getBenchmark(): Promise<BenchmarkReport> {
    return notRunReport('No authorised aggregate benchmark configured', 'live')
  }
}
