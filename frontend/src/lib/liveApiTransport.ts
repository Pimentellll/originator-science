import { TransportError } from './transport'
import type { EpisodeSession, ScientificTransport } from './transport'
import type { EpisodeSummary, PolicyComparison } from './types'
import type { ApiAction, ApiBenchmarkSummary, ApiEpisodeEvaluation, ApiPublicState, ApiRecommendation, ApiReplay, ApiStep } from './api'
import type { EpisodeRecord, PolicyComparisonRecord } from './wire'
import { adaptBenchmark, adaptComparison, adaptRecord } from './adapters'
import { recordFromReplay, reportFromSummary, seedScenario } from './fromApi'
import { canonicalPolicyKey, CANONICAL_POLICIES, policyInfo } from './actions'
import { notRunReport } from './project'

/**
 * LiveApiTransport — talks to the real MIRAGE public API (src/mirage/api/app.py,
 * feat/mirage-eval-api). Endpoints used:
 *
 *   GET  /health
 *   POST /episodes                      {seed, policy_name}   -> PublicState      (reset episode)
 *   GET  /episodes/{id}/recommendation                        -> {action}         (policy's next action)
 *   POST /episodes/{id}/actions         {action_type, candidate_id, rationale}    (take public action)
 *   GET  /episodes/{id}/replay                                -> Replay           (public trace so far / stored)
 *   GET  /episodes/{id}                                       -> PublicState
 *   GET  /benchmarks, /benchmarks/{id}                        -> aggregate results (token-gated; NOT RUN if absent)
 *   GET  /benchmarks/episodes/{id}                            -> per-episode correct-vs-justified verdict
 *                                                                (PROVISIONAL, not in H0; token-gated; only when `evaluation`)
 *
 * The API has no scenario catalogue, no policy catalogue and no comparison endpoint, so:
 *  - scenarios are seeds from `LiveConfig.seeds` (a seed fully determines the world),
 *  - `LiveConfig.policies` lists the policy keys this server is known to register. A policy
 *    comparison plays exactly those on the SAME seed through the ordinary reset / recommend /
 *    act endpoints: real public traces on identical seeded worlds. Every other canonical
 *    policy (Lookahead, PPO, ...) is NOT RUN. Availability is configured, never probed, so a
 *    missing policy costs no failed request.
 *  - aggregate results are requested only when `LiveConfig.benchmarks` is true (the endpoint is
 *    token-gated and answers 404 when disabled).
 */
export interface LiveConfig {
  base: string
  /** Seeds offered as scenarios. */
  seeds: number[]
  /** Policy keys the server registers. Offered in the cockpit (first = default) and compared. */
  policies: string[]
  /** Request /benchmarks (needs the dev proxy to carry the eval token). */
  benchmarks: boolean
  /** Request the authorised per-episode verdict once an episode is terminal (same token path). */
  evaluation: boolean
}

export const DEFAULT_LIVE_CONFIG: LiveConfig = { base: '/api', seeds: [9], policies: ['rescue_planner', 'greedy_eig', 'fixed_pipeline', 'random'], benchmarks: false, evaluation: false }

/** Safety valve while auto-playing a comparison episode. */
const MAX_COMPARE_STEPS = 40

interface LiveSession {
  episodeId: string
  seed: number
  policy: string
  codeVersion: string
  record: EpisodeRecord
}

export class LiveApiTransport implements ScientificTransport {
  readonly kind = 'live' as const
  readonly label = 'LIVE API'
  private readonly cfg: LiveConfig
  private readonly fetchImpl: typeof fetch
  private readonly sessions = new Map<string, LiveSession>()
  private readonly comparisons = new Map<string, Promise<PolicyComparison | null>>()
  private codeVersion = 'unknown'

  constructor(cfg: Partial<LiveConfig> = {}, fetchImpl: typeof fetch = (...a) => fetch(...a)) {
    this.cfg = { ...DEFAULT_LIVE_CONFIG, ...cfg, base: (cfg.base ?? DEFAULT_LIVE_CONFIG.base).replace(/\/$/, '') }
    this.fetchImpl = fetchImpl
  }

  private async request<T>(path: string, init?: RequestInit, opts: { nullOn?: number[] } = {}): Promise<T | null> {
    let res: Response
    try {
      res = await this.fetchImpl(`${this.cfg.base}${path}`, {
        ...init,
        headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...init?.headers },
      })
    } catch (e) {
      throw new TransportError(`Cannot reach the MIRAGE API at ${this.cfg.base}${path}: ${e instanceof Error ? e.message : String(e)}`)
    }
    if (opts.nullOn?.includes(res.status)) return null
    if (!res.ok) {
      let detail = ''
      try {
        const body = (await res.json()) as { detail?: unknown }
        if (typeof body.detail === 'string') detail = ` (${body.detail})`
      } catch {
        /* non-JSON error body */
      }
      throw new TransportError(`${init?.method ?? 'GET'} ${path} -> ${res.status}${detail}`, res.status)
    }
    return (await res.json()) as T
  }

  private async need<T>(path: string, init?: RequestInit): Promise<T> {
    return (await this.request<T>(path, init)) as T
  }

  async listEpisodes(): Promise<EpisodeSummary[]> {
    const h = await this.need<{ status: string; version: string }>('/health')
    if (h.status !== 'ok') throw new TransportError(`API unhealthy: ${h.status}`)
    return this.cfg.seeds.flatMap((seed) =>
      this.cfg.policies.map((name) => ({
        episode_id: `seed-${seed}:${name}`,
        scenario: seedScenario(seed),
        policy: policyInfo(name),
        seed,
        provenance: { source: 'live' as const, label: `LIVE · public API ${h.version}` },
      })),
    )
  }

  private seedOf(scenarioId: string): number {
    const m = /^seed-(\d+)$/.exec(scenarioId)
    if (!m) throw new TransportError(`Unknown scenario "${scenarioId}"`)
    return Number(m[1])
  }

  private async create(seed: number, policy: string) {
    const state = await this.need<ApiPublicState>('/episodes', { method: 'POST', body: JSON.stringify({ seed, policy_name: policy }) })
    return state
  }

  private async recommend(episodeId: string): Promise<ApiRecommendation | null> {
    return this.request<ApiRecommendation>(`/episodes/${encodeURIComponent(episodeId)}/recommendation`, undefined, { nullOn: [409] })
  }

  async openEpisode(scenarioId: string, policyName?: string): Promise<EpisodeSession> {
    const seed = this.seedOf(scenarioId)
    const policy = policyName ?? this.cfg.policies[0]
    let state: ApiPublicState
    try {
      state = await this.create(seed, policy)
    } catch (e) {
      if (e instanceof TransportError && e.status === 422) throw new TransportError(`Policy "${policy}" is not available on this server: NOT RUN.`, 422)
      throw e
    }
    const [replay, rec] = await Promise.all([this.need<ApiReplay>(`/episodes/${encodeURIComponent(state.episode_id)}/replay`), this.recommend(state.episode_id)])
    this.codeVersion = replay.code_version
    const record = adaptRecord(recordFromReplay(replay, { initial: state, recommendation: rec?.action ?? null }))
    const session_id = state.episode_id
    this.sessions.set(session_id, { episodeId: state.episode_id, seed, policy, codeVersion: this.codeVersion, record })
    return { session_id, mode: 'live', record }
  }

  async step(sessionId: string): Promise<EpisodeSession> {
    const s = this.sessions.get(sessionId)
    if (!s) throw new TransportError(`Unknown session ${sessionId}`)
    const next = s.record.pending?.recommendation
    if (!next) throw new TransportError('The policy has no recommended action to execute for this state.')
    const a = next.action
    const stepped = await this.need<ApiStep>(`/episodes/${encodeURIComponent(s.episodeId)}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action_type: a.action_type, candidate_id: a.candidate_id, rationale: next.rationale ?? undefined }),
    })
    // The replay is the authoritative public trace; the step response only supplies the new state.
    const replay = await this.need<ApiReplay>(`/episodes/${encodeURIComponent(s.episodeId)}/replay`)
    this.codeVersion = replay.code_version
    const rec = stepped.state.terminal ? null : await this.recommend(s.episodeId)
    const evaluation = stepped.state.terminal ? await this.evaluationOf(s.episodeId) : null
    const record = adaptRecord(recordFromReplay(replay, { initial: stepped.state, recommendation: rec?.action ?? null, evaluation }))
    s.record = record
    return { session_id: sessionId, mode: 'live', record }
  }

  /**
   * The authorised verdict, only when configured and only for a terminal episode. Any refusal
   * (not enabled, not authorised, not terminal) means "no verdict attached", never an error.
   */
  private async evaluationOf(episodeId: string): Promise<ApiEpisodeEvaluation | null> {
    if (!this.cfg.evaluation) return null
    return this.request<ApiEpisodeEvaluation>(`/benchmarks/episodes/${encodeURIComponent(episodeId)}`, undefined, { nullOn: [403, 404, 409] })
  }

  /** Stored or in-progress episode by id, as a scrubbable replay (`?episode=<id>`). */
  async openStored(episodeId: string): Promise<EpisodeSession> {
    const [replay, state] = await Promise.all([
      this.need<ApiReplay>(`/episodes/${encodeURIComponent(episodeId)}/replay`),
      this.request<ApiPublicState>(`/episodes/${encodeURIComponent(episodeId)}`, undefined, { nullOn: [404] }),
    ])
    const evaluation = replay.complete ? await this.evaluationOf(episodeId) : null
    const record = adaptRecord(recordFromReplay(replay, { initial: state ?? undefined, evaluation }))
    return { session_id: episodeId, mode: replay.complete ? 'replay' : 'live', record }
  }

  getPolicyComparison(scenarioId: string): Promise<PolicyComparison | null> {
    let p = this.comparisons.get(scenarioId)
    if (!p) {
      p = this.runComparison(scenarioId)
      p.catch(() => this.comparisons.delete(scenarioId))
      this.comparisons.set(scenarioId, p)
    }
    return p
  }

  /** Play one policy to its terminal decision on `seed`, via the public endpoints only. */
  private async playToEnd(seed: number, policy: string): Promise<EpisodeRecord> {
    const state = await this.create(seed, policy)
    const id = state.episode_id
    let terminal = state.terminal
    for (let i = 0; i < MAX_COMPARE_STEPS && !terminal; i++) {
      const rec = await this.recommend(id)
      if (!rec) break
      const a: ApiAction = rec.action
      const r = await this.need<ApiStep>(`/episodes/${encodeURIComponent(id)}/actions`, { method: 'POST', body: JSON.stringify({ action_type: a.action_type, candidate_id: a.candidate_id }) })
      terminal = r.state.terminal
    }
    const replay = await this.need<ApiReplay>(`/episodes/${encodeURIComponent(id)}/replay`)
    const evaluation = terminal ? await this.evaluationOf(id) : null
    return adaptRecord(recordFromReplay(replay, { initial: state, evaluation }))
  }

  private async runComparison(scenarioId: string): Promise<PolicyComparison | null> {
    const seed = this.seedOf(scenarioId)
    const records: EpisodeRecord[] = []
    const not_run: { policy_name: string; reason: string }[] = []
    const configured = new Set(this.cfg.policies.map(canonicalPolicyKey))
    for (const name of this.cfg.policies) records.push(await this.playToEnd(seed, name))
    for (const p of CANONICAL_POLICIES)
      if (!configured.has(p.key)) not_run.push({ policy_name: p.key, reason: 'Not registered on this server: no replay artifact or checkpoint exists for this policy.' })
    if (records.length < 2) return null
    const cmp: PolicyComparisonRecord = { scenario: seedScenario(seed), seed, records, not_run, provenance: records[0].provenance }
    return adaptComparison(cmp)
  }

  async getBenchmark() {
    if (!this.cfg.benchmarks) return notRunReport('Aggregate benchmark results are not enabled for this client (set VITE_MIRAGE_BENCHMARKS=1 with MIRAGE_EVAL_TOKEN on the dev proxy).', 'live')
    const ids = await this.request<string[]>('/benchmarks', undefined, { nullOn: [403, 404] })
    if (!ids) return notRunReport('Aggregate benchmark results are not enabled for this server, or this client is not authorised.', 'live')
    if (ids.length === 0) return notRunReport('The server has no benchmark summaries yet.', 'live')
    const id = [...ids].sort().at(-1)!
    const summary = await this.need<ApiBenchmarkSummary>(`/benchmarks/${encodeURIComponent(id)}`)
    return adaptBenchmark(reportFromSummary(summary, 'LIVE · authorised aggregate results'))
  }
}
