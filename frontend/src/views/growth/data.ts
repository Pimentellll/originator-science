import { useEffect, useState } from 'react'
import { createGrowthClient, type GrowthClient } from '../../lib/growth/client'

let client: GrowthClient | null = null

export function growthClient(): GrowthClient {
  client ??= createGrowthClient()
  return client
}

export type Async<T> = { state: 'loading' } | { state: 'error'; error: string } | { state: 'ready'; value: T }

/** Runs `load` whenever `key` changes and ignores results from superseded calls. */
export function useAsync<T>(key: string, load: () => Promise<T>): Async<T> {
  const [result, setResult] = useState<{ key: string; value: Async<T> }>({ key, value: { state: 'loading' } })
  useEffect(() => {
    let live = true
    load().then(
      (value) => live && setResult({ key, value: { state: 'ready', value } }),
      (e: unknown) => live && setResult({ key, value: { state: 'error', error: e instanceof Error ? e.message : String(e) } }),
    )
    return () => {
      live = false
    }
    // `load` is keyed by `key`; callers pass a fresh closure each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  return result.key === key ? result.value : { state: 'loading' }
}
