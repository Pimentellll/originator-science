import { TransportError } from './transport'
import type { EpisodeSession, ScientificTransport } from './transport'
import type { BenchmarkReport, EpisodeSummary } from './types'
import type { BenchmarkReportDto, EpisodeRecord, PolicyComparisonRecord } from './wire'
import { adaptBenchmark, adaptComparison, adaptRecord } from './adapters'
import { notRunReport, projectSummary } from './project'

/**
 * Source of recorded public episodes. A replay record is exactly
 * PROVENANCE_AND_REPLAY.md: seed, public initial state, ordered public events,
 * terminal decision, policy metadata and contract version. Playing it needs no
 * model, policy, or environment RNG.
 */
export interface ReplaySource {
  records(): Promise<EpisodeRecord[]>
  comparisons(): Promise<PolicyComparisonRecord[]>
  benchmark(): Promise<BenchmarkReportDto | null>
}

/** Reads `{base}/index.json` -> { episodes: string[], comparisons?: string[], benchmark?: string }. */
export function fetchReplaySource(base: string, fetchImpl: typeof fetch = (...a) => fetch(...a)): ReplaySource {
  const root = base.replace(/\/$/, '')
  const getJson = async (file: string) => {
    const res = await fetchImpl(`${root}/${file}`)
    if (!res.ok) throw new TransportError(`replay: ${file} -> ${res.status}`, res.status)
    return (await res.json()) as unknown
  }
  type Index = { episodes: string[]; comparisons?: string[]; benchmark?: string }
  let index: Promise<Index> | undefined
  const idx = () => (index ??= getJson('index.json') as Promise<Index>)
  return {
    records: async () => (await Promise.all((await idx()).episodes.map(getJson))) as EpisodeRecord[],
    comparisons: async () => (await Promise.all(((await idx()).comparisons ?? []).map(getJson))) as PolicyComparisonRecord[],
    benchmark: async () => {
      const f = (await idx()).benchmark
      return f ? ((await getJson(f)) as BenchmarkReportDto) : null
    },
  }
}

/** Plays back recorded episodes. The mock transport is this class over in-memory data. */
export class ReplayTransport implements ScientificTransport {
  readonly kind: 'mock' | 'replay'
  readonly label: string
  private loaded?: Promise<EpisodeRecord[]>
  private readonly sessions = new Map<string, EpisodeRecord>()

  constructor(
    private readonly source: ReplaySource,
    opts: { kind?: 'mock' | 'replay'; label?: string } = {},
  ) {
    this.kind = opts.kind ?? 'replay'
    this.label = opts.label ?? 'REPLAY'
  }

  private records() {
    return (this.loaded ??= this.source.records().then((rs) => rs.map((r) => adaptRecord(r))))
  }

  async listEpisodes(): Promise<EpisodeSummary[]> {
    return (await this.records()).map((r) => projectSummary({ episode_id: r.episode_id, scenario: r.scenario, policy: r.policy, seed: r.seed, provenance: r.provenance }))
  }

  async openEpisode(scenarioId: string, policyName?: string): Promise<EpisodeSession> {
    const rec = (await this.records()).find((r) => r.scenario.id === scenarioId && (!policyName || r.policy.name === policyName))
    if (!rec) throw new TransportError(`No recorded episode for scenario "${scenarioId}"${policyName ? ` / policy "${policyName}"` : ''}`)
    const session_id = `${rec.episode_id}#${this.sessions.size}`
    this.sessions.set(session_id, rec)
    return { session_id, mode: 'replay', record: rec }
  }

  async step(): Promise<EpisodeSession> {
    throw new TransportError('Replay sessions are complete recordings; scrub instead of stepping.')
  }

  async getPolicyComparison(scenarioId: string) {
    const c = (await this.source.comparisons()).find((x) => x.scenario.id === scenarioId)
    return adaptComparison(c ?? null)
  }

  async getBenchmark(): Promise<BenchmarkReport> {
    const b = await this.source.benchmark()
    return b ? adaptBenchmark(b) : notRunReport('No benchmark report in this replay source', this.kind === 'mock' ? 'mock' : 'recorded')
  }
}
