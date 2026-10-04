import type { Beat } from './guided'
import { beliefRows } from './derive'
import type { BeliefRow } from './derive'
import type { CockpitState } from './types'

/** The five stages a campaign moves through, in the order a first-time viewer meets them. */
export const STAGES = ['The failure', 'Run a test', 'Update belief', 'Decide', 'Verdict'] as const

const STAGE_OF: Record<Beat['kind'], number> = {
  failure: 0,
  evidence: 1,
  redesign: 1,
  update: 2,
  decision: 3,
  justification: 4,
}

export const stageOf = (beat: Beat | undefined): number => (beat ? STAGE_OF[beat.kind] : 0)

/** The beats narrating the frame on screen: every beat of the latest step at or before the cursor. */
export function beatsAt(beats: Beat[], cursor: number): Beat[] {
  const at = beats.filter((b) => b.cursor <= cursor).at(-1)?.cursor
  return at === undefined ? [] : beats.filter((b) => b.cursor === at)
}

/** Plain words for the technical terms the narration inherits from the guided demo. */
export const plain = (line: string) =>
  line
    .replace(/Starting posterior entropy/g, 'Starting uncertainty (entropy)')
    .replace(/[Pp]osterior entropy/g, 'Uncertainty (entropy)')
    .replace(/\(model posterior\)/g, "(the model's belief)")
    .replace(/the model posterior/g, "the model's belief")
    .replace(/the posterior/g, 'its belief')
    .replace(/in the posterior/g, 'in its belief')

export function headline(beat: Beat): string {
  switch (beat.kind) {
    case 'failure':
      return 'A binder failed downstream. MIRAGE has to find out why before deciding what to do with it.'
    case 'evidence':
      return `MIRAGE ran a test: ${beat.body[0]}`
    case 'update':
      return 'MIRAGE updated what it believes.'
    case 'redesign':
      return 'MIRAGE redesigned the candidate instead of discarding it.'
    case 'decision':
      return beat.body[0]
    case 'justification':
      return "The evaluator's verdict: was the decision right, and was it earned?"
  }
}

/** The headline for a whole step; a decision and its verdict share one. */
export function groupHeadline(group: Beat[]): string {
  const decision = group.find((b) => b.kind === 'decision')
  const last = group.at(-1)
  if (!last) return 'Loading the campaign…'
  if (decision && last.kind === 'justification') return `${decision.body[0]} Was it right, and was it earned?`
  return headline(last)
}

/** Lead sentences shown up front, and the rest kept behind a toggle. */
export function narrate(group: Beat[], leadLines = 2): { lead: string[]; more: string[] } {
  const lines = group.flatMap((b) => (b.kind === 'evidence' || b.kind === 'decision' || b.kind === 'failure' ? b.body.slice(1) : b.body)).map(plain)
  return { lead: lines.slice(0, leadLines), more: lines.slice(leadLines) }
}

export function topBeliefs(frame: CockpitState, prev: CockpitState | null, n = 3): BeliefRow[] {
  return beliefRows(frame, prev)
    .sort((a, b) => b.p - a.p)
    .slice(0, n)
}
