import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { SummaryBar } from './SummaryBar'
import { SessionContext } from '../state/sessionContext'
import type { SessionApi } from '../state/sessionContext'

function summary(overrides: Partial<SessionApi> = {}): SessionApi {
  return {
    transport: { kind: 'live' },
    episodes: [
      { episode_id: 'seed-9-rescue', scenario: { id: 'seed-9', title: 'Aggregation + kinetic defect' }, policy: { name: 'rescue_planner', label: 'RESCUE PLANNER', family: 'campaign' }, seed: 9, provenance: { source: 'live', label: 'Live API' } },
      { episode_id: 'seed-9-random', scenario: { id: 'seed-9', title: 'Aggregation + kinetic defect' }, policy: { name: 'random', label: 'RANDOM', family: 'baseline' }, seed: 9, provenance: { source: 'live', label: 'Live API' } },
      { episode_id: 'seed-9-lookahead', scenario: { id: 'seed-9', title: 'Aggregation + kinetic defect' }, policy: { name: 'lookahead', label: 'LOOKAHEAD', family: 'campaign' }, seed: 9, provenance: { source: 'live', label: 'Live API' } },
    ],
    scenarioId: 'seed-9',
    policyName: 'rescue_planner',
    session: null,
    frames: [],
    cursor: 0,
    frame: null,
    prevFrame: null,
    selection: null,
    phase: 'ready',
    error: null,
    playing: false,
    atEnd: true,
    canRun: false,
    comparison: null,
    comparisonError: null,
    launch: { scenario: null, semantics: null, policy: 'bogus', seed: 9, control: 'manual', guided: false },
    catalogue: null,
    catalogueState: 'ready',
    scenarioEntry: null,
    manualLog: [],
    launchCampaign: () => {},
    act: () => {},
    endGuided: () => {},
    selectScenario: () => {},
    startCampaign: () => {},
    selectPolicy: () => {},
    run: () => {},
    seek: () => {},
    reset: () => {},
    togglePlay: () => {},
    select: () => {},
    ...overrides,
  } as unknown as SessionApi
}

function markup(value: SessionApi): string {
  return renderToStaticMarkup(createElement(SessionContext.Provider, { value }, createElement(SummaryBar)))
}

function visibleText(html: string): string {
  return html.replaceAll('&quot;', '"').replaceAll('&#x27;', "'")
}

describe('presenter notices', () => {
  it('explains when an unknown URL policy fell back to the offered policy', () => {
    const html = visibleText(markup(summary()))
    expect(html).toContain('Policy "bogus" isn\'t offered by this server; showing Rescue Planner.')
  })

  it('shows the server error beside a policy selector', () => {
    const error = 'Policy "lookahead", scenario or semantics is not available on this server: NOT RUN.'
    const html = visibleText(markup(summary({ phase: 'error', error, launch: { scenario: null, semantics: null, policy: 'lookahead', seed: 9, control: 'manual', guided: false } })))
    expect(html).toContain('role="alert"')
    expect(html).toContain(error)
    expect(html).toContain('aria-label="Policy"')
    expect(html).toContain('Choose another policy from the Policy menu above.')
  })
})
