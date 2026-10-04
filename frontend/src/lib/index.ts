import { DEFAULT_LIVE_CONFIG, LiveApiTransport } from './liveApiTransport'
import { createMockTransport } from './mock'
import { fetchReplaySource, ReplayTransport } from './replayTransport'
import type { ScientificTransport } from './transport'

export type TransportKind = 'mock' | 'replay' | 'live'

/**
 * The single place that decides which backend the app talks to.
 
 */
const ints = (v: string | undefined, fallback: number[]) => {
  const out = (v ?? '')
    .split(',')
    .map((x) => x.trim())
    .filter((x) => /^\d+$/.test(x))
    .map(Number)
  return out.length ? out : fallback
}
const names = (v: string | undefined, fallback: string[]) => {
  const out = (v ?? '').split(',').map((x) => x.trim()).filter(Boolean)
  return out.length ? out : fallback
}

/**
 * The single place that decides which backend the app talks to. LIVE is the
 * default (the demo target); `?transport=mock|replay` or VITE_MIRAGE_TRANSPORT
 * selects development data.
 */
export function createTransport(kind?: TransportKind): ScientificTransport {
  const requested =
    kind ??
    (new URLSearchParams(typeof location === 'undefined' ? '' : location.search).get('transport') as TransportKind | null) ??
    (import.meta.env.VITE_MIRAGE_TRANSPORT as TransportKind | undefined) ??
    'live'

  switch (requested) {
    case 'mock':
      return createMockTransport()
    case 'replay':
      return new ReplayTransport(fetchReplaySource(import.meta.env.VITE_MIRAGE_REPLAY_BASE || '/replays'), { kind: 'replay', label: 'REPLAY' })
    default:
      return new LiveApiTransport({
        base: import.meta.env.VITE_MIRAGE_API_BASE || DEFAULT_LIVE_CONFIG.base,
        seeds: ints(import.meta.env.VITE_MIRAGE_SEEDS, DEFAULT_LIVE_CONFIG.seeds),
        policies: names(import.meta.env.VITE_MIRAGE_POLICIES, DEFAULT_LIVE_CONFIG.policies),
        benchmarks: ['1', 'true'].includes(String(import.meta.env.VITE_MIRAGE_BENCHMARKS)),
        evaluation: ['1', 'true'].includes(String(import.meta.env.VITE_MIRAGE_EVALUATION))
      })
  }
}

export type { ScientificTransport } from './transport'
