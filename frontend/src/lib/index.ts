import { LiveApiTransport } from './liveApiTransport'
import { createMockTransport } from './mock'
import { fetchReplaySource, ReplayTransport } from './replayTransport'
import type { ScientificTransport } from './transport'

export type TransportKind = 'mock' | 'replay' | 'live'

/**
 * The single place that decides which backend the app talks to.
 * `?transport=live|replay|mock` overrides VITE_MIRAGE_TRANSPORT for a session.
 */
export function createTransport(kind?: TransportKind): ScientificTransport {
  const requested =
    kind ??
    (new URLSearchParams(typeof location === 'undefined' ? '' : location.search).get('transport') as TransportKind | null) ??
    (import.meta.env.VITE_MIRAGE_TRANSPORT as TransportKind | undefined) ??
    'mock'

  switch (requested) {
    case 'live':
      return new LiveApiTransport(import.meta.env.VITE_MIRAGE_API_BASE || '/api')
    case 'replay':
      return new ReplayTransport(fetchReplaySource(import.meta.env.VITE_MIRAGE_REPLAY_BASE || '/replays'), { kind: 'replay', label: 'REPLAY' })
    default:
      return createMockTransport()
  }
}

export type { ScientificTransport } from './transport'
