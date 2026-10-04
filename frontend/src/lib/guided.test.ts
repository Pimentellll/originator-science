import { describe, expect, it } from 'vitest'
import { projectEpisode } from './project'
import { buildBeats } from './guided'
import { verdictOf } from './verdict'
import { recordFromReplay } from './fromApi'
import { adaptRecord } from './adapters'
import type { ApiReplay } from './api'
import replay from './fixtures/replay-rescue_planner-9.json'
import evaluation from './fixtures/evaluation-rescue_planner-9.json'
import state0 from './fixtures/state-9.json'
import type { ApiEpisodeEvaluation, ApiPublicState } from './api'

const frames = projectEpisode(adaptRecord(recordFromReplay(replay as unknown as ApiReplay, { initial: state0 as unknown as ApiPublicState, evaluation: evaluation as unknown as ApiEpisodeEvaluation })))

describe('guided beats are derived from the real trace', () => {
  const beats = buildBeats(frames)
  it('opens with the failure and closes with the justification', () => {
    expect(beats[0].kind).toBe('failure')
    expect(beats[0].body.join(' ')).toMatch(/molecular, experimental or biological/)
    expect(beats.at(-1)!.kind).toBe('justification')
  })
  it('follows the recorded actions in order, adding a causal update after every measurement', () => {
    const acts = frames.at(-1)!.events.slice(1).map((e) => e.kind)
    const kinds = beats.map((b) => b.kind)
    expect(kinds.filter((k) => k === 'update').length).toBe(acts.filter((k) => k === 'measurement').length)
    expect(kinds.filter((k) => k === 'redesign').length).toBe(acts.filter((k) => k === 'redesign').length)
    expect(kinds.filter((k) => k === 'decision').length).toBe(1)
  })
  it('quotes real belief numbers, not scripted ones', () => {
    const update = beats.find((b) => b.kind === 'update')!
    const e = frames[update.cursor].events[update.cursor]
    const moved = Math.max(...Object.keys(e.belief_after.p).map((m) => Math.abs(e.belief_after.p[m as keyof typeof e.belief_after.p] - e.belief_before!.p[m as keyof typeof e.belief_after.p])))
    expect(moved).toBeGreaterThan(0)
    expect(update.body[0]).toMatch(/\d\.\d\d → \d\.\d\d/)
  })
  it('only shows beats for frames revealed so far', () => {
    expect(buildBeats(frames.slice(0, 2)).every((b) => b.cursor <= 1)).toBe(true)
    expect(buildBeats(frames.slice(0, 2)).some((b) => b.kind === 'justification')).toBe(false)
  })
  it('the justification beat reports resources and unrun assays from public data', () => {
    const j = beats.at(-1)!.body.join('\n')
    expect(j).toMatch(/Resources consumed: budget/)
    expect(j).toMatch(/Assays not run:/)
    expect(j).toMatch(/Remaining uncertainty:/)
  })
})

describe('verdictOf', () => {
  const base = { terminal_correct: true as boolean | null, justified: true }
  it('maps the five display verdicts', () => {
    expect(verdictOf(base, 'REJECT').label).toBe('CORRECT + JUSTIFIED')
    expect(verdictOf({ ...base, justified: false }, 'REJECT').label).toBe('CORRECT BUT UNJUSTIFIED')
    expect(verdictOf({ terminal_correct: false, justified: false }, 'SELECT').label).toBe('INCORRECT')
    expect(verdictOf({ terminal_correct: null, justified: false, justified_abstention: true }, 'ABSTAIN').label).toBe('JUSTIFIED ABSTENTION')
    expect(verdictOf({ terminal_correct: null, justified: false }, 'ABSTAIN').label).toBe('NO VERDICT')
  })
  it('never invents a verdict when none is attached', () => {
    expect(verdictOf(null, 'REJECT').kind).toBe('no_verdict')
  })
})
