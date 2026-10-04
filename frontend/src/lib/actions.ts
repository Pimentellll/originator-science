import type { ActionType } from './wire'
import type { EventKind, Mechanism, PolicyInfo } from './types'

/**
 * Presentation knowledge about the frozen action set. The only place that knows
 * how to label an ActionType or which mechanisms an assay informs
 * (docs/scientific-spec/ASSAY_MODELS.md). Unknown actions degrade to a
 * humanised name.
 */
interface ActionMeta {
  label: string
  /** Short chip text. */
  short: string
  kind: EventKind
  informs: Mechanism[]
}

const META: Record<ActionType, ActionMeta> = {
  MEASURE_STABILITY: { label: 'Measure stability', short: 'STAB', kind: 'measurement', informs: ['folding'] },
  MEASURE_SEC: { label: 'Size-exclusion (SEC)', short: 'SEC', kind: 'measurement', informs: ['aggregation'] },
  MEASURE_SPR: { label: 'Surface plasmon resonance (SPR)', short: 'SPR', kind: 'measurement', informs: ['affinity', 'kinetic', 'aggregation'] },
  MEASURE_EPITOPE: { label: 'Measure epitope engagement', short: 'EPI', kind: 'measurement', informs: ['epitope'] },
  MEASURE_DEVELOPABILITY: { label: 'Measure developability', short: 'DEV', kind: 'measurement', informs: ['developability'] },
  VALIDATE_ASSAY: { label: 'Validate assay (control)', short: 'CTRL', kind: 'measurement', informs: ['assay_invalid'] },
  ORTHOGONAL_FUNCTION: { label: 'Orthogonal function assay', short: 'ORTH', kind: 'measurement', informs: ['assay_invalid', 'model_invalid'] },
  REDESIGN_STABILITY: { label: 'Redesign for stability', short: 'REDESIGN', kind: 'redesign', informs: ['folding'] },
  REDESIGN_SOLUBILITY: { label: 'Redesign for solubility', short: 'REDESIGN', kind: 'redesign', informs: ['aggregation', 'developability'] },
  REDESIGN_INTERFACE: { label: 'Redesign interface', short: 'REDESIGN', kind: 'redesign', informs: ['affinity', 'kinetic'] },
  SELECT: { label: 'Select candidate', short: 'SELECT', kind: 'decision', informs: [] },
  REJECT: { label: 'Reject candidate', short: 'REJECT', kind: 'decision', informs: [] },
  MODEL_INVALID: { label: 'Declare model invalid', short: 'MODEL ✕', kind: 'decision', informs: [] },
  ABSTAIN: { label: 'Abstain', short: 'ABSTAIN', kind: 'decision', informs: [] },
}

const humanise = (s: string) => s.toLowerCase().replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())

export const actionLabel = (a: ActionType) => META[a]?.label ?? humanise(a)
export const actionShort = (a: ActionType) => META[a]?.short ?? a
export const actionKind = (a: ActionType): EventKind => META[a]?.kind ?? 'measurement'
/** Mechanisms the action targets (redesign) or informs (assay). */
export const actionInforms = (a: ActionType): Mechanism[] => META[a]?.informs ?? []
export const isTerminalAction = (a: ActionType) => actionKind(a) === 'decision'

// ---------------------------------------------------------------- policies

const POLICY_LABELS: Record<string, string> = {
  RandomPolicy: 'RANDOM',
  FixedPipelinePolicy: 'FIXED PIPELINE',
  GreedyEIGPolicy: 'GREEDY EIG',
  PPOPolicy: 'MIRAGE PPO',
  ClaudeScientistPolicy: 'CLAUDE SCIENTIST',
}

export function policyInfo(name: string, description?: string): PolicyInfo {
  return { name, label: POLICY_LABELS[name] ?? name, description }
}

// ------------------------------------------------------------ measurements

interface MeasurementMeta {
  label: string
  digits: number
}

const MEASUREMENTS: Record<string, MeasurementMeta> = {
  stability_proxy: { label: 'stability proxy', digits: 2 },
  monomer_fraction: { label: 'monomer fraction', digits: 2 },
  log_kd: { label: 'log KD', digits: 2 },
  log_koff: { label: 'log koff', digits: 2 },
  epitope_signal: { label: 'epitope signal', digits: 2 },
  liability_proxy: { label: 'liability proxy', digits: 2 },
  control_signal: { label: 'control signal', digits: 2 },
  orthogonal_function_signal: { label: 'orthogonal function', digits: 2 },
}

export function measurementLabel(name: string): string {
  return MEASUREMENTS[name]?.label ?? name.replace(/_/g, ' ')
}

export function formatMeasurement(name: string, value: number): string {
  return value.toFixed(MEASUREMENTS[name]?.digits ?? 3).replace('-', '−')
}

/** `quality` is a free-form public string; this is the one place it is interpreted. */
export function isPoorQuality(quality: string): boolean {
  return /degrad|poor|unreli|low|bad|noisy|invalid/i.test(quality)
}
