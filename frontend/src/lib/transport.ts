import type { BenchmarkReport, EpisodeSummary, PolicyComparison, SessionMode } from './types'
import type { EpisodeRecord } from './wire'

/**
 * The ONLY seam between the UI and a backend. Components never fetch, and never
 * see wire DTOs: transports hand back validated public EpisodeRecords, and
 * `lib/project.ts` turns those into frontend state.
 */
export interface EpisodeSession {
  session_id: string
  mode: SessionMode
  /** Public record so far. Replay: complete. Live: grows with `step()`. */
  record: EpisodeRecord
}

export interface ScientificTransport {
  readonly kind: 'mock' | 'replay' | 'live'
  readonly label: string

  listEpisodes(): Promise<EpisodeSummary[]>

  /** Start (live) or load (replay) an episode. `policyName` defaults to the scenario's featured policy. */
  openEpisode(scenarioId: string, policyName?: string): Promise<EpisodeSession>

  /** Live only: execute the policy's recommended action and return the extended record. */
  step(sessionId: string): Promise<EpisodeSession>

  /** Same seeded world under several policies. null => NOT RUN. */
  getPolicyComparison(scenarioId: string): Promise<PolicyComparison | null>

  /** Authorised aggregate results. status 'not_run' when nothing exists. */
  getBenchmark(): Promise<BenchmarkReport>
}

export class TransportError extends Error {
  readonly status?: number
  constructor(message: string, status?: number) {
    super(message)
    this.name = 'TransportError'
    this.status = status
  }
}
