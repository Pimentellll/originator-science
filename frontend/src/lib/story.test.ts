import { describe, expect, it } from 'vitest'
import type { Beat } from './guided'
import { beatsAt, groupHeadline, headline, narrate, plain, stageOf, topBeliefs } from './story'
import { MECHANISMS } from './types'
import type { CockpitState } from './types'

const beat = (id: string, kind: Beat['kind'], cursor: number, body: string[] = [`${id} line`]): Beat => ({
  id,
  kind,
  cursor,
  body,
  heading: id.toUpperCase(),
  focus: 'evidence',
})

const beats = [
  beat('failure', 'failure', 0),
  beat('e1', 'evidence', 1, ['SEC on C-0.', 'Reading: 0.42.', 'Cost: 1.']),
  beat('u1', 'update', 1, ['Posterior entropy 2.0 → 1.5.']),
  beat('d', 'decision', 2, ['MIRAGE rejects C-0.', 'Basis: x.']),
]

describe('story narration', () => {
  it('shows every beat of the latest step at or before the cursor', () => {
    expect(beatsAt(beats, 0).map((b) => b.id)).toEqual(['failure'])
    expect(beatsAt(beats, 1).map((b) => b.id)).toEqual(['e1', 'u1'])
    expect(beatsAt(beats, 9).map((b) => b.id)).toEqual(['d'])
    expect(beatsAt([], 3)).toEqual([])
  })

  it('maps the step tracker stage from the last beat of the step', () => {
    expect(stageOf(undefined)).toBe(0)
    expect(stageOf(beatsAt(beats, 1).at(-1))).toBe(2)
    expect(stageOf(beat('j', 'justification', 2))).toBe(4)
  })

  it('leads with the reading, hides the rest, and drops the line already in the headline', () => {
    const { lead, more } = narrate(beatsAt(beats, 1))
    expect(headline(beats[1])).toBe('MIRAGE ran a test: SEC on C-0.')
    expect(lead).toEqual(['Reading: 0.42.', 'Cost: 1.'])
    expect(more).toEqual(['Uncertainty (entropy) 2.0 → 1.5.'])
    expect(narrate(beatsAt(beats, 2)).lead).toEqual(['Basis: x.'])
  })

  it('names the decision in the verdict headline and does not repeat the failure headline', () => {
    expect(groupHeadline([beats[3], beat('j', 'justification', 2)])).toBe('MIRAGE rejects C-0. Was it right, and was it earned?')
    expect(groupHeadline([])).toBe('Loading the campaign…')
    expect(narrate([beat('f', 'failure', 0, ['The binder failed.', 'Cause unknown.'])]).lead).toEqual(['Cause unknown.'])
  })

  it('replaces posterior jargon with plain words', () => {
    expect(plain('Starting posterior entropy 4.75: open.')).toBe('Starting uncertainty (entropy) 4.75: open.')
    expect(plain('Basis: Folding at 0.70 (model posterior).')).toBe("Basis: Folding at 0.70 (the model's belief).")
  })

  it('ranks the top beliefs by probability', () => {
    const p = Object.fromEntries(MECHANISMS.map((m, i) => [m, i / 10]))
    const frame = { belief: { p } } as unknown as CockpitState
    const top = topBeliefs(frame, null, 3)
    expect(top.map((r) => r.mechanism)).toEqual([...MECHANISMS].reverse().slice(0, 3))
    expect(top[0].delta).toBeNull()
  })
})
