import { DEFAULT_LIVE_CONFIG } from '../liveApiTransport'
import { TransportError } from '../transport'
import type {
  AutoplayResult,
  Condition,
  DiagnosisBody,
  GrowthEpisode,
  GrowthGrid,
  GrowthRun,
  GrowthRunEntry,
  MeasureResponse,
  SandboxCreated,
  SandboxVerdict,
  SubmitResponse,
} from './types'

export interface GrowthSandbox {
  create(body: { preset?: 'demo-BP' | 'demo-MA'; seed?: number; condition?: Condition }): Promise<SandboxCreated>
  measure(
    sessionId: string,
    body: { time_h: number; dilution_factor: number; replicates: number },
  ): Promise<MeasureResponse>
  diagnose(sessionId: string, body: DiagnosisBody): Promise<SubmitResponse>
  verdict(sessionId: string): Promise<SandboxVerdict>
  autoplay(sessionId: string, agent: 'good_scientist' | 'passive_bayes'): Promise<AutoplayResult>
}

export interface GrowthClient {
  readonly kind: 'live' | 'static'
  listRuns(): Promise<GrowthRunEntry[]>
  getRun(runId: string): Promise<GrowthRun>
  getEpisode(runId: string, episodeId: string): Promise<GrowthEpisode>
  getGrid(matrix: string): Promise<GrowthGrid>
  readonly sandbox: GrowthSandbox | null
}

export interface GrowthClientOptions {
  fetch?: typeof fetch
  liveBase?: string
  staticBase?: string
  search?: string
}

function segment(value: string): string {
  return encodeURIComponent(value)
}

async function requestJson<T>(fetchImpl: typeof fetch, url: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let response: Response
  try {
    response = await fetchImpl(url, { ...init, headers })
  } catch (error) {
    throw new TransportError(
      `Cannot reach the MIRAGE API at ${url}: ${error instanceof Error ? error.message : String(error)}`,
    )
  }

  if (!response.ok) {
    let detail = ''
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = ` (${body.detail})`
    } catch {
      // Non-JSON error responses have no detail field.
    }
    throw new TransportError(`${init.method ?? 'GET'} ${url} -> ${response.status}${detail}`, response.status)
  }
  return (await response.json()) as T
}

function createLiveClient(base: string, fetchImpl: typeof fetch): GrowthClient {
  const root = base.replace(/\/$/, '')
  const get = <T>(path: string) => requestJson<T>(fetchImpl, `${root}${path}`)
  const post = <T>(path: string, body: unknown) =>
    requestJson<T>(fetchImpl, `${root}${path}`, {
      method: 'POST',
      body: JSON.stringify(body),
    })

  const sandbox: GrowthSandbox = {
    create: (body) => post<SandboxCreated>('/growth/sandbox', body),
    measure: (sessionId, body) =>
      post<MeasureResponse>(`/growth/sandbox/${segment(sessionId)}/measure`, body),
    diagnose: (sessionId, body) =>
      post<SubmitResponse>(`/growth/sandbox/${segment(sessionId)}/diagnose`, body),
    verdict: (sessionId) => get<SandboxVerdict>(`/benchmarks/growth/sandbox/${segment(sessionId)}/verdict`),
    autoplay: (sessionId, agent) =>
      post<AutoplayResult>(`/benchmarks/growth/sandbox/${segment(sessionId)}/autoplay`, { agent }),
  }

  return {
    kind: 'live',
    listRuns: () => get<GrowthRunEntry[]>('/benchmarks/growth/runs'),
    getRun: (runId) => get<GrowthRun>(`/benchmarks/growth/runs/${segment(runId)}`),
    getEpisode: (runId, episodeId) =>
      get<GrowthEpisode>(
        `/benchmarks/growth/runs/${segment(runId)}/episodes/${segment(episodeId)}`,
      ),
    getGrid: (matrix) => get<GrowthGrid>(`/benchmarks/growth/grid?matrix=${segment(matrix)}`),
    sandbox,
  }
}

function createStaticClient(base: string, fetchImpl: typeof fetch): GrowthClient {
  const root = base.replace(/\/+$/, '')
  const get = <T>(file: string) => requestJson<T>(fetchImpl, `${root}/${file}`)

  return {
    kind: 'static',
    listRuns: () => get<GrowthRunEntry[]>('runs.json'),
    getRun: (runId) => get<GrowthRun>(`runs/${segment(runId)}.json`),
    getEpisode: (runId, episodeId) =>
      get<GrowthEpisode>(`runs/${segment(runId)}/episodes/${segment(episodeId)}.json`),
    getGrid: (matrix) => get<GrowthGrid>(`grid-${segment(matrix)}.json`),
    sandbox: null,
  }
}

export function createGrowthClient(options: GrowthClientOptions = {}): GrowthClient {
  const fetchImpl = options.fetch ?? globalThis.fetch.bind(globalThis)
  const search = options.search ?? (typeof window === 'undefined' ? '' : window.location.search)
  const staticMode =
    new URLSearchParams(search).get('growth') === 'static' || import.meta.env.VITE_MIRAGE_GROWTH === 'static'

  if (staticMode) {
    const base = options.staticBase ?? (import.meta.env.VITE_MIRAGE_GROWTH_DATA || '/growth-data')
    return createStaticClient(base, fetchImpl)
  }

  const base = options.liveBase ?? (import.meta.env.VITE_MIRAGE_API_BASE || DEFAULT_LIVE_CONFIG.base)
  return createLiveClient(base, fetchImpl)
}
