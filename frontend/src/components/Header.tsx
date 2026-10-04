import { useSession } from '../state/sessionContext'
import type { Route } from '../state/route'
import { ModePill, ProvenancePill } from './ui'
import { fmtMoney, fmtT } from '../lib/format'

const TABS: { id: Route; label: string }[] = [
  { id: 'cockpit', label: 'COCKPIT' },
  { id: 'compare', label: 'COMPARE POLICIES' },
  { id: 'benchmark', label: 'BENCHMARK LAB' },
]

export function Header({ route, navigate }: { route: Route; navigate: (r: Route) => void }) {
  const s = useSession()
  const f = s.frame
  const scenarios = Array.from(new Map(s.episodes.map((e) => [e.scenario.id, e.scenario])).values())
  const policies = s.episodes.filter((e) => e.scenario.id === s.scenarioId).map((e) => e.policy)
  const r = f?.resources
  const budgetUsed = r ? r.budget.total - r.budget.remaining : 0
  const sampleUsed = r ? r.sample.total - r.sample.remaining : 0

  return (
    <header className="hdr">
      <div className="hdr__brand">
        <span className="hdr__logo">
          MIRAG<i>E</i>
        </span>
        <span className="hdr__ver">Scientific Cockpit</span>
      </div>
      <nav className="hdr__nav" aria-label="Views">
        {TABS.map((t) => (
          <button key={t.id} className="hdr__tab" aria-current={route === t.id ? 'page' : undefined} onClick={() => navigate(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      <label className="hdr__field">
        <span className="hdr__label">Scenario</span>
        <select className="hdr__select" value={s.scenarioId ?? ''} onChange={(e) => s.selectScenario(e.target.value)} aria-label="Scenario">
          {scenarios.map((sc) => (
            <option key={sc.id} value={sc.id}>
              {sc.title}
            </option>
          ))}
        </select>
      </label>

      <label className="hdr__field">
        <span className="hdr__label">Active policy</span>
        {policies.length > 1 ? (
          <select className="hdr__select" value={s.policyName ?? ''} onChange={(e) => s.selectPolicy(e.target.value)} aria-label="Policy">
            {policies.map((p) => (
              <option key={p.name} value={p.name}>
                {p.label}
              </option>
            ))}
          </select>
        ) : (
          <span className="hdr__static">{f?.policy.label ?? '—'}</span>
        )}
      </label>

      {s.session && <ModePill mode={s.session.mode} />}
      {f && <ProvenancePill provenance={f.provenance} />}
      {!f && s.transport.kind === 'mock' && <span className="pill pill--mock">DEV / MOCK</span>}

      <div className="hdr__spacer" />

      {f && r && (
        <div className="hdr__stats" aria-label="Campaign resources">
          <div className={`hdr__stat ${r.budget.remaining / r.budget.total < 0.15 ? 'hdr__stat--warn' : ''}`}>
            <span className="hdr__label">Budget</span>
            <b>
              {fmtMoney(budgetUsed)} <small>/ {fmtMoney(r.budget.total)}</small>
            </b>
          </div>
          <div className="hdr__stat">
            <span className="hdr__label">Sample</span>
            <b>
              {sampleUsed} <small>/ {r.sample.total} µg</small>
            </b>
          </div>
          <div className="hdr__stat">
            <span className="hdr__label">Sim. time</span>
            <b>{fmtT(r.time.elapsed)}</b>
          </div>
          <div className="hdr__stat">
            <span className="hdr__label">Step</span>
            <b>
              {f.step} {f.total_steps !== null && <small>/ {f.total_steps}</small>}
            </b>
          </div>
          <div className="hdr__stat">
            <span className="hdr__label">Seed</span>
            <b>{f.seed}</b>
          </div>
        </div>
      )}
    </header>
  )
}
