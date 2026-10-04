import type { GrowthRunEntry } from '../../lib/growth/types'

export type AgentMeta = { code: string; name: string; kind: string }

const MODELS: Record<string, AgentMeta> = {
  'claude-opus-5-5': { code: 'C1', name: 'Claude Opus 5.5', kind: 'LLM agent · prompt-v2 · effort high' },
  'claude-sonnet-5-5': { code: 'C2', name: 'Claude Sonnet 5.5', kind: 'LLM agent · prompt-v2 · effort high' },
}
const SCRIPTED: Record<string, AgentMeta> = {
  good_scientist: { code: 'B1', name: 'GoodScientist', kind: 'scripted · always dilutes late' },
  passive_bayes: { code: 'B2', name: 'PassiveBayes', kind: 'scripted · reads the undiluted curve only' },
}

export function agentMeta(agent: string | null, model?: string | null): AgentMeta {
  if (model && MODELS[model]) return MODELS[model]
  if (agent && SCRIPTED[agent]) return SCRIPTED[agent]
  return { code: '—', name: model ?? agent ?? 'unknown agent', kind: agent ?? '' }
}

export function runMeta(run: Pick<GrowthRunEntry, 'agent' | 'model'>): AgentMeta {
  return agentMeta(run.agent, run.model)
}

export const DIAG_LABEL: Record<string, string> = {
  BIOMASS_AS_READ: 'biomass as read',
  BIOMASS_ABOVE_READING: 'biomass above reading',
}

export const CONDITION_LABEL: Record<string, string> = {
  BIOLOGICAL_PLATEAU: 'biological plateau',
  MEASUREMENT_ARTIFACT: 'reader saturation (measurement artefact)',
}

export function fmt(v: number | null | undefined, digits = 3): string {
  return v === null || v === undefined || Number.isNaN(v) ? '—' : v.toFixed(digits)
}

export function frac(k: number, n: number) {
  return `${k}/${n}`
}
