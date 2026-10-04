import type { BenchmarkReport, Catalogue, EpisodeSummary, PolicyComparison, SessionMode, SystemReport } from './types'
import type { ActionType, EpisodeRecord } from './wire'

/** Orchestration options for a live campaign. The backend never shows these to a policy. */
export interface OpenOptions {
  scenario?: string | null
  semantics?: string | null
}

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
  /** Live only: the actions the public state currently allows (for the manual scientist). */
  available_actions?: ActionType[]
}

export interface ScientificTransport {
  readonly kind: 'mock' | 'replay' | 'live'
  readonly label: string

  listEpisodes(): Promise<EpisodeSummary[]>

  /** Start (live) or load (replay) an episode. `policyName` defaults to the scenario's featured policy. */
  openEpisode(scenarioId: string, policyName?: string, options?: OpenOptions): Promise<EpisodeSession>

  /** Live only: execute the policy's recommended action and return the extended record. */
  step(sessionId: string): Promise<EpisodeSession>

  /** Live only: execute a person-chosen action (MANUAL SCIENTIST) and return the extended record. */
  act?(sessionId: string, action: ActionType, rationale?: string): Promise<EpisodeSession>

  /** Same seeded world under several policies. null => NOT RUN. */
  getPolicyComparison(scenarioId: string, options?: OpenOptions): Promise<PolicyComparison | null>

  /** Live only: version, policy and scenario catalogues from the public/system routes. */
  catalogue?(): Promise<Catalogue>

  /** Live only: public system self-checks (never hidden state). */
  diagnostics?(): Promise<SystemReport>

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
