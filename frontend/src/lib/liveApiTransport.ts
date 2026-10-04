import { TransportError } from './transport'
import type { EpisodeSession, OpenOptions, ScientificTransport } from './transport'
import type { Catalogue, EpisodeSummary, PolicyComparison, PolicyEntry, ScenarioEntry, SystemCheck, SystemReport } from './types'
import type { ApiAction, ApiBenchmarkSummary, ApiDiagnostics, ApiEpisodeEvaluation, ApiPolicy, ApiPublicState, ApiRecommendation, ApiReplay, ApiScenario, ApiStep, ApiVersion } from './api'
import type { ActionType, EpisodeRecord, PolicyComparisonRecord } from './wire'
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
 *  GET  /policies, /scenarios, /version, /diagnostics  -> public/system catalogue (orchestration metadata)
 *
 * There is no comparison endpoint, so:
 *  - scenarios are seeds from `LiveConfig.seeds` (a seed fully determines the world),
 *  - the policies on offer come from GET /policies (only those flagged `available`). Servers that
 *    predate that route fall back to `LiveConfig.policies`. A policy comparison plays exactly the
 *    available policies on the SAME seed through the ordinary reset / recommend / act endpoints:
 *    real public traces on identical seeded worlds. Every other canonical policy (Lookahead,
 *    PPO, ...) is NOT RUN.
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
  available: ActionType[]
}

export class LiveApiTransport implements ScientificTransport {
  readonly kind = 'live' as const
  readonly label = 'LIVE API'
  private readonly cfg: LiveConfig
  private readonly fetchImpl: typeof fetch
  private readonly sessions = new Map<string, LiveSession>()
  private readonly comparisons = new Map<string, Promise<PolicyComparison | null>>()
  private codeVersion = 'unknown'
  /** Policies this server offers (from /policies when present, else the configured list). */
  private policyNames: string[] | null = null
  private catalogueCache: Promise<Catalogue> | null = null

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

  /** Public catalogue; each route is optional so older servers still work. */
  catalogue(): Promise<Catalogue> {
    this.catalogueCache ??= (async () => {
      const [v, p, s] = await Promise.all([
        this.request<ApiVersion>('/version', undefined, { nullOn: [404] }).catch(() => null),
        this.request<ApiPolicy[]>('/policies', undefined, { nullOn: [404] }).catch(() => null),
        this.request<ApiScenario[]>('/scenarios', undefined, { nullOn: [404] }).catch(() => null),
      ])
      const policies: PolicyEntry[] | null = p ? p.map((x) => ({ name: x.name, label: policyInfo(x.name).label, kind: x.kind, available: x.available, description: x.description, reason: x.reason })) : null
      const scenarios: ScenarioEntry[] | null = s ? s.map((x) => ({ id: x.id, title: x.title, summary: x.summary, cli_name: x.cli_name, is_default: x.is_default ?? false })) : null
      return {
        version: v
          ? { mirage_version: v.mirage_version, git_sha: v.git_sha, git_dirty: v.git_dirty, commit_date: v.commit_date, api_version: v.api_version, contract_version: v.contract_version, semantics_default: v.scenario_semantics_default, semantics_available: v.scenario_semantics_available, python_version: v.python_version }
          : null,
        policies,
        scenarios,
      }
    })()
    this.catalogueCache.catch(() => (this.catalogueCache = null))
    return this.catalogueCache
  }

  private async offered(): Promise<string[]> {
    if (!this.policyNames) {
      const cat = await this.catalogue().catch(() => null)
      const names = cat?.policies?.filter((x) => x.available).map((x) => x.name)
      this.policyNames = names && names.length ? names : this.cfg.policies
    }
    return this.policyNames
  }

  async diagnostics(): Promise<SystemReport> {
    const cat = await this.catalogue().catch(() => ({ version: null, policies: null, scenarios: null }) as Catalogue)
    let reachable = false
    const checks: SystemCheck[] = []
    try {
      const h = await this.request<{ status: string }>('/health')
      reachable = h?.status === 'ok'
      checks.push({ name: 'API reachable', status: reachable ? 'pass' : 'fail', detail: reachable ? 'GET /health ok' : `status ${h?.status}` })
    } catch (e) {
      checks.push({ name: 'API reachable', status: 'fail', detail: e instanceof Error ? e.message : String(e) })
      return { reachable, checks, catalogue: cat }
    }
    const d = await this.request<ApiDiagnostics>('/diagnostics', undefined, { nullOn: [404] }).catch(() => null)
    if (!d) {
      checks.push({ name: 'self-checks', status: 'skip', detail: 'this server has no /diagnostics route' })
      return { reachable, checks, catalogue: cat }
    }
    const labels: Record<string, string> = {
      environment: 'Environment initialised',
      deterministic_smoke: 'Deterministic smoke',
      record_replay: 'Record / replay operational',
      leak_guard: 'Public leakage guard',
      policies: 'Policies available',
    }
    for (const c of d.checks) if (c.name !== 'api') checks.push({ name: labels[c.name] ?? c.name, status: c.status as SystemCheck['status'], detail: c.detail })
    return { reachable, checks, catalogue: cat, note: d.note }
  }

  async listEpisodes(): Promise<EpisodeSummary[]> {
    const h = await this.need<{ status: string; version: string }>('/health')
    if (h.status !== 'ok') throw new TransportError(`API unhealthy: ${h.status}`)
    const offered = await this.offered()
    return this.cfg.seeds.flatMap((seed) =>
      offered.map((name) => ({
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

  private async create(seed: number, policy: string, options: OpenOptions = {}) {
    const body = { seed, policy_name: policy, ...(options.scenario ? { scenario: options.scenario } : {}), ...(options.semantics ? { scenario_version: options.semantics } : {}) }
    return this.need<ApiPublicState>('/episodes', { method: 'POST', body: JSON.stringify(body) })
  }

  private async recommend(episodeId: string): Promise<ApiRecommendation | null> {
    return this.request<ApiRecommendation>(`/episodes/${encodeURIComponent(episodeId)}/recommendation`, undefined, { nullOn: [409] })
  }

  async openEpisode(scenarioId: string, policyName?: string, options: OpenOptions = {}): Promise<EpisodeSession> {
    const seed = this.seedOf(scenarioId)
    const policy = policyName ?? (await this.offered())[0]
    let state: ApiPublicState
    try {
      state = await this.create(seed, policy, options)
    } catch (e) {
      if (e instanceof TransportError && e.status === 422) throw new TransportError(`Policy "${policy}", scenario or semantics is not available on this server: NOT RUN.`, 422)
      throw e
    }
    const [replay, rec] = await Promise.all([this.need<ApiReplay>(`/episodes/${encodeURIComponent(state.episode_id)}/replay`), this.recommend(state.episode_id)])
    this.codeVersion = replay.code_version
    const record = adaptRecord(recordFromReplay(replay, { initial: state, recommendation: rec?.action ?? null }))
    const session_id = state.episode_id
    const available = state.available_actions.map((a) => a.action_type)
    this.sessions.set(session_id, { episodeId: state.episode_id, seed, policy, codeVersion: this.codeVersion, record, available })
    return { session_id, mode: 'live', record, available_actions: available }
  }

  async step(sessionId: string): Promise<EpisodeSession> {
    const s = this.sessions.get(sessionId)
    if (!s) throw new TransportError(`Unknown session ${sessionId}`)
    const next = s.record.pending?.recommendation
    if (!next) throw new TransportError('The policy has no recommended action to execute for this state.')
    return this.execute(sessionId, s, next.action.action_type, next.action.candidate_id, next.rationale ?? undefined)
  }

  /** MANUAL SCIENTIST: the person picks any action the public state allows. */
  async act(sessionId: string, action: ActionType, rationale = 'manual scientist'): Promise<EpisodeSession> {
    const s = this.sessions.get(sessionId)
    if (!s) throw new TransportError(`Unknown session ${sessionId}`)
    if (!s.available.includes(action)) throw new TransportError(`${action} is not available in the current public state.`)
    return this.execute(sessionId, s, action, null, rationale)
  }

  private async execute(sessionId: string, s: LiveSession, actionType: ActionType, candidateId: string | null, rationale?: string): Promise<EpisodeSession> {
    const stepped = await this.need<ApiStep>(`/episodes/${encodeURIComponent(s.episodeId)}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action_type: actionType, candidate_id: candidateId ?? undefined, rationale }),
    })
    // The replay is the authoritative public trace; the step response only supplies the new state.
    const replay = await this.need<ApiReplay>(`/episodes/${encodeURIComponent(s.episodeId)}/replay`)
    this.codeVersion = replay.code_version
    const rec = stepped.state.terminal ? null : await this.recommend(s.episodeId)
    const evaluation = stepped.state.terminal ? await this.evaluationOf(s.episodeId) : null
    const record = adaptRecord(recordFromReplay(replay, { initial: stepped.state, recommendation: rec?.action ?? null, evaluation }))
    s.record = record
    s.available = stepped.state.available_actions.map((a) => a.action_type)
    return { session_id: sessionId, mode: 'live', record, available_actions: s.available }
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

  getPolicyComparison(scenarioId: string, options: OpenOptions = {}): Promise<PolicyComparison | null> {
    const key = `${scenarioId}|${options.scenario ?? ''}|${options.semantics ?? ''}`
    let p = this.comparisons.get(key)
    if (!p) {
      p = this.runComparison(scenarioId, options)
      p.catch(() => this.comparisons.delete(key))
      this.comparisons.set(key, p)
    }
    return p
  }

  /** Play one policy to its terminal decision on `seed`, via the public endpoints only. */
  private async playToEnd(seed: number, policy: string, options: OpenOptions): Promise<EpisodeRecord> {
    const state = await this.create(seed, policy, options)
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

  private async runComparison(scenarioId: string, options: OpenOptions): Promise<PolicyComparison | null> {
    const seed = this.seedOf(scenarioId)
    const records: EpisodeRecord[] = []
    const not_run: { policy_name: string; reason: string }[] = []
    const offered = await this.offered()
    const configured = new Set(offered.map(canonicalPolicyKey))
    for (const name of offered) records.push(await this.playToEnd(seed, name, options))
    for (const p of CANONICAL_POLICIES)
      if (!configured.has(p.key)) not_run.push({ policy_name: p.key, reason: 'Not registered on this server: no replay artifact or checkpoint exists for this policy.' })
    if (records.length < 2) return null
    const cmp: PolicyComparisonRecord = { scenario: seedScenario(seed), seed, records, not_run, provenance: records[0].provenance }
    return adaptComparison(cmp)
  }

  async getBenchmark() {
    if (!this.cfg.benchmarks) return notRunReport('Start the live demo and run `./mirage benchmark-dev` to generate the development-split aggregate.', 'live')
    const ids = await this.request<string[]>('/benchmarks', undefined, { nullOn: [403, 404] })
    if (!ids) return notRunReport('The development benchmark store is not available. Restart with `./mirage demo`, then run `./mirage benchmark-dev`.', 'live')
    if (ids.length === 0) return notRunReport('The development-split benchmark hasn\'t been generated yet. `./mirage demo` generates it automatically about 30 seconds after starting; refresh this page then. Otherwise run `./mirage benchmark-dev` from the repository root.', 'live')
    const id = [...ids].sort().at(-1)!
    const summary = await this.need<ApiBenchmarkSummary>(`/benchmarks/${encodeURIComponent(id)}`)
    return adaptBenchmark(reportFromSummary(summary, 'LIVE · authorised aggregate results'))
  }
}
