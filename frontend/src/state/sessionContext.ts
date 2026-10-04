import { createContext, useContext } from 'react'
import type { EpisodeSession, ScientificTransport } from '../lib/transport'
import type { CockpitState, EpisodeSummary, PolicyComparison } from '../lib/types'

export type Phase = 'loading' | 'ready' | 'running' | 'error'

export interface SessionApi {
  transport: ScientificTransport
  episodes: EpisodeSummary[]
  scenarioId: string | null
  policyName: string | null
  session: EpisodeSession | null
  frames: CockpitState[]
  cursor: number
  frame: CockpitState | null
  prevFrame: CockpitState | null
  /** Event id (`s3`), observation node id (`s3:obs`) or mechanism node id (`m:kinetic`). */
  selection: string | null
  phase: Phase
  error: string | null
  playing: boolean
  atEnd: boolean
  canRun: boolean
  /** Identical-seed comparison for the open scenario. undefined = loading, null = NOT RUN. */
  comparison: PolicyComparison | null | undefined
  /** Set when the comparison could not be produced (distinct from NOT RUN, which is `comparison === null`). */
  comparisonError: string | null
  selectScenario: (id: string) => void
  /** Reset the campaign on `seed` (a fresh episode, same policy). Live transports only. */
  startCampaign: (seed: number) => void
  selectPolicy: (name: string) => void
  run: () => void
  seek: (i: number) => void
  reset: () => void
  togglePlay: () => void
  select: (id: string | null) => void
}

export const SessionContext = createContext<SessionApi | null>(null)

export function useSession(): SessionApi {
  const v = useContext(SessionContext)
  if (!v) throw new Error('useSession outside SessionProvider')
  return v
}

