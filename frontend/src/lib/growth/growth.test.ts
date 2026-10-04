import { describe, expect, it } from 'vitest'
import { TransportError } from '../transport'
import { createGrowthClient } from './client'
import {
  conditionFor,
  dilutionAgreement,
  episodeReadingsCsv,
  foldOverUndiluted,
  hypothesisFor,
  meanBrier,
  outcome,
  passiveAt,
  reliability,
  toCsv,
} from './analysis'
import type { DerivedMeasurement, GrowthEpisode, Reading, ToolEvent } from './types'

const passive: Reading[] = [
  {
    source: 'passive',
    request_index: null,
    time_h: 12,
    dilution_factor: 1,
    readings: [0.7765],
    mean_reading: 0.7765,
    cost_units: 0,
    budget_remaining: 6,
  },
  {
    source: 'passive',
    request_index: null,
    time_h: 18,
    dilution_factor: 1,
    readings: [0.7524],
    mean_reading: 0.7524,
    cost_units: 0,
    budget_remaining: 6,
  },
]

const derived: DerivedMeasurement[] = [
  {
    event_index: 0,
    turn: 1,
    time_h: 18,
    dilution_factor: 10,
    replicates: 2,
    mean_reading: 0.2639,
    back_corrected: 2.639,
  },
  {
    event_index: 1,
    turn: 2,
    time_h: 18,
    dilution_factor: 20,
    replicates: 2,
    mean_reading: 0.1286,
    back_corrected: 2.572,
  },
  {
    event_index: 2,
    turn: 3,
    time_h: 12,
    dilution_factor: 10,
    replicates: 2,
    mean_reading: 0.2575,
    back_corrected: 2.575,
  },
]

function measureEvent(
  index: number,
  turn: number,
  time_h: number,
  dilution_factor: number,
  readings: number[],
  mean_reading: number,
): ToolEvent {
  return {
    index,
    turn,
    tool: 'measure_od',
    arguments: { time_h, dilution_factor, replicates: readings.length },
    ok: true,
    result: { time_h, dilution_factor, readings, mean_reading },
    error: null,
  }
}

describe('growth analysis', () => {
  it('maps conditions and hypotheses in both directions', () => {
    expect(hypothesisFor('BIOLOGICAL_PLATEAU')).toBe('BIOMASS_AS_READ')
    expect(hypothesisFor('MEASUREMENT_ARTIFACT')).toBe('BIOMASS_ABOVE_READING')
    expect(conditionFor('BIOMASS_AS_READ')).toBe('BIOLOGICAL_PLATEAU')
    expect(conditionFor('BIOMASS_ABOVE_READING')).toBe('MEASUREMENT_ARTIFACT')
  })

  it('classifies outcome states', () => {
    expect(outcome({ correct: null, justified: null, status: 'NO_DIAGNOSIS' })).toBe('none')
    expect(outcome({ correct: false, justified: false, status: 'DIAGNOSED' })).toBe('wrong')
    expect(outcome({ correct: true, justified: true, status: 'DIAGNOSED' })).toBe('justified')
    expect(outcome({ correct: true, justified: false, status: 'DIAGNOSED' })).toBe('unjustified')
    expect(outcome({ correct: true, justified: null, status: 'DIAGNOSED' })).toBe('unjustified')
  })

  it('gets passive readings by exact hour and computes fold-over-undiluted', () => {
    expect(passiveAt(passive, 18)).toBe(0.7524)
    expect(passiveAt(passive, 12)).toBe(0.7765)
    expect(passiveAt(passive, 11)).toBeNull()
    expect(foldOverUndiluted(derived[0], passive)).toBeCloseTo(3.507, 3)
    expect(foldOverUndiluted({ ...derived[0], time_h: 9 }, passive)).toBeNull()
  })

  it('computes dilution agreement for the real s500001-MA measurements', () => {
    const agreement = dilutionAgreement([
      ...derived,
      { ...derived[0], event_index: 3, dilution_factor: 10, back_corrected: null },
    ])
    expect(agreement).toHaveLength(1)
    expect(agreement[0].time_h).toBe(18)
    expect(agreement[0].factors).toEqual([10, 20])
    expect(agreement[0].values).toEqual([2.639, 2.572])
    expect(agreement[0].relSpread).toBeCloseTo(0.0257, 4)
  })

  it('bins reliability rows lower-inclusively, includes p=1 in the final bin, and skips null p', () => {
    const bins = reliability([
      { p: 0.19, condition: 'BIOLOGICAL_PLATEAU' },
      { p: 0.2, condition: 'MEASUREMENT_ARTIFACT' },
      { p: 0.9, condition: 'BIOLOGICAL_PLATEAU' },
      { p: 1, condition: 'MEASUREMENT_ARTIFACT' },
      { p: null, condition: 'MEASUREMENT_ARTIFACT' },
    ])
    expect(bins).toEqual([
      { lo: 0, hi: 0.2, n: 1, meanP: 0.19, observed: 0 },
      { lo: 0.2, hi: 0.4, n: 1, meanP: 0.2, observed: 1 },
      { lo: 0.4, hi: 0.6, n: 0, meanP: null, observed: null },
      { lo: 0.6, hi: 0.8, n: 0, meanP: null, observed: null },
      { lo: 0.8, hi: 1, n: 2, meanP: 0.95, observed: 0.5 },
    ])
  })

  it('averages non-null Brier scores and returns null when none are present', () => {
    expect(meanBrier([{ brier: null }, { brier: 0.25 }, { brier: 1 }])).toBe(0.625)
    expect(meanBrier([{ brier: null }])).toBeNull()
  })

  it('quotes CSV fields according to RFC 4180 and emits empty values for nulls', () => {
    expect(
      toCsv(['name', 'note', 'empty'], [
        { name: 'scientist, 1', note: 'said "OD600"\r\nnext', empty: null },
      ]),
    ).toBe('name,note,empty\r\n"scientist, 1","said ""OD600""\r\nnext",')
  })

  it('exports one row per passive and measurement replicate for s500001-MA', () => {
    const episode = {
      passive,
      events: [
        measureEvent(0, 1, 18, 10, [0.2611, 0.2667], 0.2639),
        measureEvent(1, 2, 18, 20, [0.1338, 0.1235], 0.1286),
        measureEvent(2, 3, 12, 10, [0.2627, 0.2523], 0.2575),
        { ...measureEvent(3, 4, 18, 10, [], 0), ok: false },
      ],
    } as unknown as GrowthEpisode
    const rows = episodeReadingsCsv(episode).split('\r\n')
    expect(rows[0]).toBe(
      'source,time_h,dilution_factor,replicate,reading,mean_reading,back_corrected,turn',
    )
    expect(rows).toHaveLength(9)
    expect(rows[1]).toBe('passive,12,1,1,0.7765,0.7765,0.7765,')
    expect(rows[3]).toBe('measurement,18,10,1,0.2611,0.2639,2.639,1')
    expect(rows[5]).toBe('measurement,18,20,1,0.1338,0.1286,2.572,2')
    expect(rows[7]).toBe('measurement,12,10,1,0.2627,0.2575,2.575,3')
  })
})

const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

describe('growth clients', () => {
  it('builds static data URLs and has no sandbox operations', async () => {
    const urls: string[] = []
    const fetchImpl: typeof fetch = async (input) => {
      urls.push(String(input))
      return jsonResponse({})
    }
    const client = createGrowthClient({
      search: '?growth=static',
      staticBase: '/offline-growth',
      fetch: fetchImpl,
    })

    expect(client.kind).toBe('static')
    expect(client.sandbox).toBeNull()
    await client.listRuns()
    await client.listExploratory()
    await client.getRun('run one/blue')
    await client.getEpisode('run one', 'ep ?#/2')
    await client.getGrid('strong matrix')
    expect(urls).toEqual([
      '/offline-growth/runs.json',
      '/offline-growth/exploratory.json',
      '/offline-growth/runs/run%20one%2Fblue.json',
      '/offline-growth/runs/run%20one/episodes/ep%20%3F%23%2F2.json',
      '/offline-growth/grid-strong%20matrix.json',
    ])
  })

  it('builds live evaluator and public sandbox URLs with encoded path segments', async () => {
    const calls: Array<{ url: string; method: string; body?: string }> = []
    const fetchImpl: typeof fetch = async (input, init) => {
      calls.push({
        url: String(input),
        method: init?.method ?? 'GET',
        body: typeof init?.body === 'string' ? init.body : undefined,
      })
      return jsonResponse({})
    }
    const client = createGrowthClient({ liveBase: '/api', search: '', fetch: fetchImpl })
    await client.listRuns()
    await client.listExploratory()
    await client.getRun('run/1')
    await client.getEpisode('run/1', 'ep 1')
    await client.getGrid('strong')
    await client.sandbox!.create({ seed: 123, condition: 'BIOLOGICAL_PLATEAU' })
    await client.sandbox!.measure('session/1', { time_h: 18, dilution_factor: 10, replicates: 2 })
    await client.sandbox!.diagnose('session 1', {
      diagnosis: 'BIOMASS_ABOVE_READING',
      p_biomass_above_reading: 0.9,
      late_biomass_estimate_od: null,
      rationale: 'dilution controls agree',
    })
    await client.sandbox!.verdict('session/1')
    await client.sandbox!.autoplay('session 1', 'good_scientist')

    expect(calls.map(({ url, method }) => [method, url])).toEqual([
      ['GET', '/api/benchmarks/growth/runs'],
      ['GET', '/api/benchmarks/growth/exploratory'],
      ['GET', '/api/benchmarks/growth/runs/run%2F1'],
      ['GET', '/api/benchmarks/growth/runs/run%2F1/episodes/ep%201'],
      ['GET', '/api/benchmarks/growth/grid?matrix=strong'],
      ['POST', '/api/growth/sandbox'],
      ['POST', '/api/growth/sandbox/session%2F1/measure'],
      ['POST', '/api/growth/sandbox/session%201/diagnose'],
      ['GET', '/api/benchmarks/growth/sandbox/session%2F1/verdict'],
      ['POST', '/api/benchmarks/growth/sandbox/session%201/autoplay'],
    ])
    expect(JSON.parse(calls[9].body ?? '{}')).toEqual({ agent: 'good_scientist' })
  })

  it('throws TransportError with HTTP status and the server detail', async () => {
    const client = createGrowthClient({
      search: '',
      fetch: async () => jsonResponse({ detail: 'not authorised' }, 403),
    })
    const request = client.listRuns()
    await expect(request).rejects.toBeInstanceOf(TransportError)
    await expect(request).rejects.toMatchObject({ status: 403 })
    await expect(request).rejects.toThrow('not authorised')
  })
})
