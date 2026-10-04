export type Condition = 'BIOLOGICAL_PLATEAU' | 'MEASUREMENT_ARTIFACT'
export type DiagnosisLabel = 'BIOMASS_AS_READ' | 'BIOMASS_ABOVE_READING'
export type EpisodeStatus = 'DIAGNOSED' | 'NO_DIAGNOSIS' | 'API_FAILURE' | 'REFUSED'

export interface Rate {
  k: number
  n: number
  rate: number
  wilson95: [number, number]
}

export interface GrowthRunEntry {
  run_id: string
  group: string
  agent: string | null
  model: string | null
  effort: string | null
  prompt_version: string | null
  matrix: string | null
  n_episodes: number
  frozen: boolean
  headline: {
    M1: Rate
    M2: Rate
    M3: Rate
    Q1: number | null
  } | null
  brier_mean: number | null
}

export interface RunEpisodeRow {
  episode_id: string
  condition: Condition
  seed: number
  status: EpisodeStatus
  diagnosis: DiagnosisLabel | null
  p_biomass_above_reading: number | null
  late_biomass_estimate_od: number | null
  scores: Scores
}

export interface GrowthRun {
  run: GrowthRunEntry
  manifest: Record<string, unknown>
  summary: Record<string, unknown> | null
  episodes: RunEpisodeRow[]
}

export interface EpisodeConfig {
  episode_id: string
  seed: number
  condition: Condition
  scenario_version: string
  scenario_sha256: string
  k_ratio: number
  growth: {
    r_per_h: number
    x0_odeq: number
    k_odeq: number
    nu: number
  }
  assay: {
    s_odeq: number
    n: number
    sigma_abs: number
    sigma_rel: number
    resolution: number
    eps_lin: number
    y_loq: number
  }
}

export interface Reading {
  source: 'passive' | 'agent'
  request_index: number | null
  time_h: number
  dilution_factor: number
  readings: number[]
  mean_reading: number
  cost_units: number
  budget_remaining: number
}

export interface ToolEvent {
  index: number
  turn: number
  tool: string
  arguments: Record<string, unknown>
  ok: boolean
  result: Record<string, unknown> | null
  error: string | null
}

export interface AuditItem {
  event_index: number
  request_index: number
  latent_biomass_odeq: number
  presented_biomass_odeq: number
  noise_free_reading: number
  is_late: boolean
  is_diluted: boolean
  in_diagnostic_set: boolean
  before_diagnosis: boolean
  diagnostic_control: boolean
  in_useful_region: boolean
  reconstruction_adequate: boolean
}

export interface Diagnosis {
  diagnosis: DiagnosisLabel
  p_biomass_above_reading: number
  late_biomass_estimate_od: number | null
  rationale: string
}

export interface Scores {
  correct: boolean
  diagnostic_control: boolean
  justified: boolean
  reconstruction_adequate: boolean
  cost_units: number
  measure_calls_before_diagnosis: number
  brier: number | null
  m5_diagnosticity: number | null
}

export interface DerivedMeasurement {
  event_index: number
  turn: number
  time_h: number | null
  dilution_factor: number | null
  replicates: number | null
  mean_reading: number | null
  back_corrected: number | null
}

export interface DerivedEpisodeData {
  latent_curve: [number, number][]
  reading_curve: [number, number][]
  measurements: DerivedMeasurement[]
}

export interface GrowthEpisode {
  agent: {
    name: string
    kind: 'llm' | 'scripted'
    model: string | null
    effort: string | null
    prompt_version: string | null
    prompt_sha256: string | null
    sdk_version: string | null
  }
  audit: AuditItem[]
  diagnosis: Diagnosis | null
  episode: EpisodeConfig
  events: ToolEvent[]
  llm_transcript: Array<Record<string, unknown>> | null
  passive: Reading[]
  run_meta: Record<string, unknown>
  schema_version: 'episode-result-v2'
  scores: Scores
  status: EpisodeStatus
  versions: Record<string, string>
  derived: DerivedEpisodeData
}

export interface GridColumn {
  run_id: string
  agent: string | null
  model: string | null
}

export interface GridCell {
  status: EpisodeStatus
  correct: boolean | null
  justified: boolean | null
  diagnostic_control: boolean | null
}

export interface GridRow {
  episode_id: string
  seed: number
  condition: Condition
  cells: Record<string, GridCell>
}

export interface GrowthGrid {
  columns: GridColumn[]
  rows: GridRow[]
}

export interface SandboxObservation {
  passive_readings: Reading[]
  budget_total: number
  budget_remaining: number
}

export interface SandboxCreated {
  session_id: string
  sandbox: true
  observation: SandboxObservation
}

export interface MeasureResult {
  time_h: number
  dilution_factor: number
  readings: number[]
  mean_reading: number
  budget_remaining: number
}

export interface MeasureResponse {
  ok: boolean
  result: MeasureResult | null
  error: string | null
}

export interface SubmitSuccess {
  status: EpisodeStatus
  diagnosis: Diagnosis
  events: ToolEvent[]
  passive: Reading[]
}

export interface ToolErrorResponse {
  ok: false
  result: Record<string, unknown> | null
  error: string | null
}

export type SubmitResponse = SubmitSuccess | ToolErrorResponse

export interface Reveal {
  condition: Condition
  growth: EpisodeConfig['growth']
  assay: EpisodeConfig['assay']
  k_ratio: number
  latent_curve: [number, number][]
  reading_curve: [number, number][]
}

export interface SandboxVerdict {
  episode: EpisodeConfig
  audit: AuditItem[]
  scores: Scores
  reveal: Reveal
}

export type AutoplayResult = Omit<GrowthEpisode, 'derived'> & { reveal: Reveal }

export interface DiagnosisBody {
  diagnosis: DiagnosisLabel
  p_biomass_above_reading: number
  late_biomass_estimate_od: number | null
  rationale: string
}
