import { useCallback, useEffect, useState } from 'react'

export type Route = 'cockpit' | 'compare' | 'benchmark'
const ROUTES: Route[] = ['cockpit', 'compare', 'benchmark']

function parse(): Route {
  const h = location.hash.replace(/^#\/?/, '') as Route
  return ROUTES.includes(h) ? h : 'cockpit'
}

export function useRoute(): [Route, (r: Route) => void] {
  const [route, setRoute] = useState<Route>(parse)
  useEffect(() => {
    const on = () => setRoute(parse())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  const navigate = useCallback((r: Route) => {
    location.hash = `/${r}`
  }, [])
  return [route, navigate]
}
