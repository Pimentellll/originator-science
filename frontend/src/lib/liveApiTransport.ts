import { TransportError } from './transport'
import type { EpisodeSession, ScientificTransport } from './transport'
import { adaptBenchmark, adaptComparison, adaptRecord, adaptSummaries } from './adapters'
import { notRunReport } from './project'

/**
 * LiveApiTransport — E1.
 *
 * PROVISIONAL endpoint map for the planned operations in FRONTEND_API_CONTRACT.md
 * (reset episode, read public state, take public action, read stored replay,
 * read authorised aggregate benchmark results). Reconcile here and in
 * adapters.ts when the API lands; nothing else should change.
 *
 *   GET  {base}/scenarios                          -> EpisodeSummaryDto[]
 *   POST {base}/episodes {scenario_id, policy_name?}-> {session_id, mode, record}
 *   POST {base}/episodes/{id}/actions {action}     -> {session_id, mode, record}   (take public action)
 *   GET  {base}/episodes/{id}                      -> {session_id, mode, record}   (read public state / stored replay)
 *   GET  {base}/scenarios/{id}/compare             -> PolicyComparisonRecord | 404
 *   GET  {base}/benchmark                          -> BenchmarkReportDto | 404 (=> NOT RUN)
 *
 * Every record is validated (public-only, contiguous, resource accounting)
 * before it reaches the UI. A `mode: "replay"` response with a complete record
 * is scrubbed locally and never stepped.
 */
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

  private async request(path: string, init?: RequestInit, opts: { nullOn404?: boolean } = {}): Promise<unknown> {
    let res: Response
    try {
      res = await this.fetchImpl(`${this.base}${path}`, {
        ...init,
        headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...init?.headers },
      })
    } catch (e) {
      throw new TransportError(`Cannot reach backend at ${this.base}${path}: ${e instanceof Error ? e.message : String(e)}`)
    }
    if (res.status === 404 && opts.nullOn404) return null
    if (!res.ok) throw new TransportError(`${init?.method ?? 'GET'} ${path} -> ${res.status} ${res.statusText}`, res.status)
    return res.json()
  }

  private session(raw: unknown): EpisodeSession {
    const r = raw as { session_id?: unknown; mode?: unknown; record?: unknown }
    if (!r || typeof r.session_id !== 'string') throw new TransportError('session: missing session_id')
    const s: EpisodeSession = { session_id: r.session_id, mode: r.mode === 'replay' ? 'replay' : 'live', record: adaptRecord(r.record) }
    this.sessions.set(s.session_id, s)
    return s
  }

  async listEpisodes() {
    return adaptSummaries(await this.request('/scenarios'))
  }

  async openEpisode(scenarioId: string, policyName?: string) {
    return this.session(await this.request('/episodes', { method: 'POST', body: JSON.stringify({ scenario_id: scenarioId, policy_name: policyName }) }))
  }

  async step(sessionId: string) {
    const current = this.sessions.get(sessionId)
    const rec = current?.record.pending?.recommendation
    if (!rec) throw new TransportError('No recommended action to execute for this session')
    return this.session(await this.request(`/episodes/${encodeURIComponent(sessionId)}/actions`, { method: 'POST', body: JSON.stringify({ action: rec.action }) }))
  }

  async getPolicyComparison(scenarioId: string) {
    return adaptComparison(await this.request(`/scenarios/${encodeURIComponent(scenarioId)}/compare`, undefined, { nullOn404: true }))
  }

  async getBenchmark() {
    const raw = await this.request('/benchmark', undefined, { nullOn404: true })
    return raw === null ? notRunReport('Backend has no benchmark report', 'live') : adaptBenchmark(raw)
  }
}
