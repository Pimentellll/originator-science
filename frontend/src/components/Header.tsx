import { useSession } from '../state/sessionContext'
import { BINDER_ROUTES } from '../state/route'
import type { Route } from '../state/route'

const GROUPS: { label: string; tabs: { id: Route; label: string }[] }[] = [
  {
    label: 'Growth benchmark',
    tabs: [
      { id: 'results', label: 'Results' },
      { id: 'lab', label: 'Lab' },
      { id: 'method', label: 'Method' },
    ],
  },
  {
    label: 'Binder campaign',
    tabs: [
      { id: 'launch', label: 'Start' },
      { id: 'cockpit', label: 'Cockpit' },
      { id: 'compare', label: 'Compare policies' },
      { id: 'benchmark', label: 'Benchmark lab' },
      { id: 'diagnostics', label: 'System check' },
    ],
  },
]


export function Header({ route, navigate, growthKind }: { route: Route; navigate: (r: Route) => void; growthKind: 'live' | 'static' }) {
  const binder = BINDER_ROUTES.includes(route)
  const session = useSession()
  const transportLabel = session.transport.kind === 'live' ? 'live · MIRAGE API' : session.transport.label.toLowerCase()
  const current = route === 'episode' ? 'results' : route
  return (
    <header className="hdr">
      <div className="hdr__brand">
        <span className="hdr__logo">
          MIRAG<i>E</i>
        </span>
        <div className="hdr__tags">
          <span className="hdr__tag1">
            <b>Does the agent know when it is wrong?</b> Benchmarks for scientific agents
          </span>
        </div>
      </div>
      <nav className="hdr__nav" aria-label="Views">
        {GROUPS.map((g) => (
          <div className="hdr__group" key={g.label} role="group" aria-label={g.label}>
            <span className="hdr__glabel">{g.label}</span>
            {g.tabs.map((t) => (
              <button key={t.id} className="hdr__tab" aria-current={current === t.id ? 'page' : undefined} onClick={() => navigate(t.id)}>
                {t.label}
              </button>
            ))}
          </div>
        ))}
      </nav>
      <div className="hdr__spacer" />
      {binder ? (
        <span className="hdr__meta mono">{transportLabel}</span>
      ) : (
        <span className="hdr__meta mono">{growthKind === 'static' ? 'offline · static export' : 'live · MIRAGE API'}</span>
      )}
    </header>
  )
}
