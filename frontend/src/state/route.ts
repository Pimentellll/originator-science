import { useCallback, useEffect, useState } from 'react'

export type Route = 'overview' | 'results' | 'episode' | 'lab' | 'method' | 'launch' | 'cockpit' | 'compare' | 'benchmark' | 'diagnostics'
/** Routes of the receptor-binder campaign app (the rest are the growth benchmark). */
export const BINDER_ROUTES: readonly Route[] = ['launch', 'cockpit', 'compare', 'benchmark', 'diagnostics']
const ROUTES: readonly Route[] = ['overview', 'results', 'episode', 'lab', 'method', 'launch', 'cockpit', 'compare', 'benchmark', 'diagnostics']

function decodeSegment(segment: string): string {
  try {
    return decodeURIComponent(segment)
  } catch {
    return segment
  }
}

/**
 * `?transport=live` is the URL `./mirage demo` opens: with no hash it lands on the launcher, not the
 * Overview page. Everything else opens the Overview.
 */
export function defaultRoute(search: string): Route {
  const q = new URLSearchParams(search)
  if (q.get('transport') !== 'live') return 'overview'
  return q.get('guided') === '1' ? 'cockpit' : 'launch'
}

export function parseHash(hash: string, search = typeof window === 'undefined' ? '' : window.location.search): { route: Route; params: string[] } {
  const path = hash.replace(/^#/, '').replace(/^\/+/, '')
  const [candidate, ...segments] = path.split('/').filter(Boolean)
  if (!candidate || !ROUTES.includes(candidate as Route)) {
    return { route: defaultRoute(search), params: [] }
  }
  return { route: candidate as Route, params: segments.map(decodeSegment) }
}

export function useRoute(): [Route, (r: Route, ...params: string[]) => void, string[]] {
  const [location, setLocation] = useState(() => parseHash(window.location.hash))
  useEffect(() => {
    const on = () => setLocation(parseHash(window.location.hash))
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  const navigate = useCallback((r: Route, ...params: string[]) => {
    window.location.hash = `/${[r, ...params].map(encodeURIComponent).join('/')}`
  }, [])
  return [location.route, navigate, location.params]
}
