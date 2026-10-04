import { createContext, useContext } from 'react'
import type { EpisodeSession, ScientificTransport } from '../lib/transport'
import type { ActionType } from '../lib/wire'
import type { Catalogue, CockpitState, EpisodeSummary, LaunchConfig, PolicyComparison, ScenarioEntry } from '../lib/types'

export type Phase = 'loading' | 'ready' | 'running' | 'error'

/** One MANUAL SCIENTIST decision next to what the policy would have done from the same public state. */
export interface ManualChoice {
  step: number
  chosen: ActionType
  recommended: ActionType | null
}

/** The deterministic guided demo: fixed seed, fixed scenario, MIRAGE drives. */
export const GUIDED_PRESET: Omit<LaunchConfig, 'guided'> = {
  scenario: 'aggregation_kinetic_defect',
  semantics: 'SEMANTICS_V2',
  policy: 'rescue_planner',
  seed: 9,
  control: 'auto',
}

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
  /** Orchestration choices of the human running the demo (never policy input). */
  launch: LaunchConfig
  /** Public/system catalogue from the backend; null while loading or when the transport has none. */
  catalogue: Catalogue | null
  catalogueState: 'loading' | 'ready' | 'unavailable'
  /** The scenario entry matching `launch.scenario` (or the server default). */
  scenarioEntry: ScenarioEntry | null
  manualLog: ManualChoice[]
  /** Start a campaign with these choices (unspecified fields keep their current value). */
  launchCampaign: (cfg: Partial<LaunchConfig>) => void
  /** MANUAL SCIENTIST: execute an action the public state allows. */
  act: (action: ActionType) => void
  endGuided: () => void
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

