import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ManualLog } from '../components/ManualControls'
import type { ActionType } from '../lib/wire'
import { SessionContext } from './sessionContext'
import type { ManualChoice, SessionApi } from './sessionContext'
import { appendManualChoice } from './manual'

describe('manual comparison', () => {
  it('lists and counts a terminal decision after a manual run', () => {
    const choices: [ActionType, ActionType | null][] = [
      ['MEASURE_SEC', 'MEASURE_SEC'],
      ['MEASURE_DEVELOPABILITY', 'MEASURE_DEVELOPABILITY'],
      ['REDESIGN_SOLUBILITY', 'MEASURE_SPR'],
      ['MEASURE_SPR', 'MEASURE_SPR'],
      ['REJECT', null],
    ]
    const log = choices.reduce<ManualChoice[]>((entries, [chosen, recommended], index) => appendManualChoice(entries, index + 1, chosen, recommended), [])
    const context = { manualLog: log } as unknown as SessionApi
    const html = renderToStaticMarkup(createElement(SessionContext.Provider, { value: context }, createElement(ManualLog)))

    expect(log).toHaveLength(5)
    expect(log.at(-1)).toEqual({ step: 5, chosen: 'REJECT', recommended: null })
    expect(html).toContain('matched 3 of 5')
    expect(html).toContain('you: <b>REJECT</b>')
    expect(html).toContain('MIRAGE: —')
  })
})
