import { useCallback, useEffect, useState } from 'react'

export type Route = 'overview' | 'results' | 'episode' | 'lab' | 'method' | 'cockpit' | 'compare' | 'benchmark'
const ROUTES: readonly Route[] = ['overview', 'results', 'episode', 'lab', 'method', 'cockpit', 'compare', 'benchmark']

function decodeSegment(segment: string): string {
  try {
    return decodeURIComponent(segment)
  } catch {
    return segment
  }
}

export function parseHash(hash: string): { route: Route; params: string[] } {
  const path = hash.replace(/^#/, '').replace(/^\/+/, '')
  const [candidate, ...segments] = path.split('/').filter(Boolean)
  if (!candidate || !ROUTES.includes(candidate as Route)) {
    return { route: 'overview', params: [] }
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
